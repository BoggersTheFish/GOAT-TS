from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

from src.graph.client import NebulaGraphClient
from src.graph.cognition import EDGE_IN_WAVE, WAVE_SOURCE_REASONING
from src.graph.models import Edge, MemoryState, Node, Triple, Wave
from src.ingestion.llm_extract import TripleExtractor
from src.monitoring.metrics import graph_edge_count, graph_node_count, query_latency_seconds, tension_score
from src.reasoning.cache import CacheAdapter
from src.reasoning.tension import TensionResult, compute_tension
from src.utils import load_yaml_config

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class Hypothesis:
    prompt: str
    rationale: str


@dataclass(slots=True)
class ReasoningResponse:
    query: str
    activated_nodes: list[str]
    hypotheses: list[Hypothesis]
    tension: TensionResult
    graph_context: dict[str, int]


def activate_from_query(query: str, triples: list[Triple]) -> list[str]:
    lowered_query = query.lower()
    activated: list[str] = []
    for triple in triples:
        if (
            triple.subject.lower() in lowered_query
            or triple.object.lower() in lowered_query
            or triple.relation.lower() in lowered_query
        ):
            activated.extend([triple.subject, triple.object])
    return sorted(set(activated))


def generate_hypotheses(tension: TensionResult, limit: int) -> list[Hypothesis]:
    hypotheses: list[Hypothesis] = []
    for src, dst, delta in tension.high_tension_pairs[:limit]:
        hypotheses.append(
            Hypothesis(
                prompt=f"What evidence explains the conflict between {src} and {dst}?",
                rationale=f"Observed tension contribution {delta:.4f} exceeds expected coupling.",
            )
        )
    return hypotheses


# Learning feedback: reweight edges involved in high-tension (contradiction) pairs
REWEIGHT_CONFLICT_DELTA = 0.2

# Words that match almost every label and should not be used for graph/keyword filtering
_LABEL_STOPWORDS = frozenset({
    "the", "and", "for", "are", "but", "not", "you", "all", "can", "had", "her", "his",
    "was", "one", "our", "out", "has", "him", "how", "its", "may", "new", "now", "old",
    "see", "way", "who", "did", "get", "got", "let", "put", "say", "she", "too", "use",
})


def _edge_weight_to_seed(node_id: str, seed_ids: set[str], edges: list[Edge]) -> float:
    best = 0.0
    for edge in edges:
        if edge.src_id == node_id and edge.dst_id in seed_ids:
            best = max(best, float(edge.weight))
        elif edge.dst_id == node_id and edge.src_id in seed_ids:
            best = max(best, float(edge.weight))
    return best


def _gravity_link_score(node: Node, seed_ids: set[str]) -> float:
    links = (node.metadata or {}).get("gravity_links") or {}
    best = 0.0
    for seed_id in seed_ids:
        details = links.get(seed_id) or {}
        best = max(best, float(details.get("gravity_value", 0.0) or 0.0))
    return best


def _merge_nodes(primary: list[Node], extra: list[Node], limit: int) -> list[Node]:
    out: list[Node] = []
    seen: set[str] = set()
    for node in primary + extra:
        if node.node_id in seen:
            continue
        out.append(node)
        seen.add(node.node_id)
        if len(out) >= limit:
            break
    return out


def _merge_edges(primary: list[Edge], extra: list[Edge], limit: int) -> list[Edge]:
    out: list[Edge] = []
    seen: set[tuple[str, str, str]] = set()
    for edge in primary + extra:
        key = (edge.src_id, edge.dst_id, edge.relation)
        if key in seen:
            continue
        out.append(edge)
        seen.add(key)
        if len(out) >= limit:
            break
    return out


def _expand_contextual_nodes(
    client: NebulaGraphClient,
    seed_nodes: list[Node],
    current_nodes: list[Node],
    current_edges: list[Edge],
    *,
    node_limit: int,
    edge_limit: int,
) -> tuple[list[Node], list[Edge], set[str]]:
    seed_ids = {node.node_id for node in seed_nodes}
    neighbor_ids: set[str] = set()
    for edge in current_edges:
        if edge.src_id in seed_ids:
            neighbor_ids.add(edge.dst_id)
        if edge.dst_id in seed_ids:
            neighbor_ids.add(edge.src_id)
    for seed_id in seed_ids:
        try:
            neighbor_ids.update(client.neighbors(seed_id))
        except Exception:
            pass
    neighbor_ids -= seed_ids

    known_by_id = {node.node_id: node for node in current_nodes}
    missing_ids = [node_id for node_id in neighbor_ids if node_id not in known_by_id]
    fetched_neighbors = client.get_nodes_by_ids(missing_ids) if missing_ids else []
    ranked_neighbors = sorted(
        [known_by_id[nid] for nid in neighbor_ids if nid in known_by_id] + fetched_neighbors,
        key=lambda node: (
            _edge_weight_to_seed(node.node_id, seed_ids, current_edges),
            _gravity_link_score(node, seed_ids),
            node.activation,
            node.mass,
        ),
        reverse=True,
    )

    selected_nodes = _merge_nodes(seed_nodes, ranked_neighbors, node_limit)
    selected_ids = {node.node_id for node in selected_nodes}
    contextual_edges = [
        edge for edge in current_edges
        if edge.src_id in selected_ids and edge.dst_id in selected_ids
    ]
    contextual_edges = _merge_edges(
        contextual_edges,
        client.list_edges_between(selected_ids, limit=edge_limit),
        edge_limit,
    )
    return selected_nodes, contextual_edges, seed_ids


def _gravity_recontextualize(
    client: NebulaGraphClient,
    selected_nodes: list[Node],
    selected_edges: list[Edge],
    candidate_nodes: list[Node],
    seed_ids: set[str],
    *,
    node_limit: int,
    edge_limit: int,
) -> tuple[list[Node], list[Edge]]:
    selected_ids = {node.node_id for node in selected_nodes}
    all_candidates = _merge_nodes(candidate_nodes, client.list_nodes(limit=node_limit), node_limit * 2)
    gravity_candidates = [
        node for node in all_candidates
        if node.node_id not in selected_ids and _gravity_link_score(node, seed_ids) > 0.0
    ]
    gravity_candidates.sort(
        key=lambda node: (
            _gravity_link_score(node, seed_ids),
            node.activation,
            node.mass,
        ),
        reverse=True,
    )
    final_nodes = _merge_nodes(selected_nodes, gravity_candidates, node_limit)
    final_ids = {node.node_id for node in final_nodes}
    final_edges = _merge_edges(
        selected_edges,
        client.list_edges_between(final_ids, limit=edge_limit),
        edge_limit,
    )
    return final_nodes, final_edges


def _query_terms(query: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[A-Za-z0-9]+", query.lower())
        if len(token) >= 3 and token not in _LABEL_STOPWORDS
    }


def retrieve_graph_context(
    query: str,
    config_root: Path,
    live: bool,
    node_limit: int | None = None,
    edge_limit: int | None = None,
    *,
    extra_keywords: list[str] | None = None,
) -> tuple[list[Node], list[Edge]]:
    """
    Retrieve a bounded, query-conditioned subgraph for reasoning.

    The function prefers:
    - label and cluster matches for the query,
    - concepts that participate in waves whose labels match the query, and
    - nodes that are well-connected and already activated,
    while keeping node/edge counts within limits from `reasoning.yaml`.
    """
    reasoning_config = load_yaml_config(config_root / "configs" / "reasoning.yaml")["reasoning"]
    if node_limit is None:
        node_limit = int(reasoning_config.get("node_limit", 200))
    if edge_limit is None:
        edge_limit = int(reasoning_config.get("edge_limit", 1000))
    client = NebulaGraphClient(
        config_root / "configs" / "graph.yaml",
        dry_run_override=not live if live else None,
    )
    terms = _query_terms(query)
    if extra_keywords:
        terms = terms | {
            t.lower().strip() for t in extra_keywords
            if len(t.strip()) >= 3 and t.lower().strip() not in _LABEL_STOPWORDS
        }
    label_keywords = list(terms) if (live and terms) else None
    cluster_ids: list[str] | None = None
    # Call-context: when live, prefer concept nodes from clusters whose topic matches the query
    if live and terms:
        cluster_nodes = client.list_cluster_nodes(limit=500)
        if cluster_nodes:
            lower_labels = {c.node_id: c.label.lower() for c in cluster_nodes}
            matching_cluster_ids = [
                cid for cid, lab in lower_labels.items()
                if any(t in lab for t in terms)
            ]
            if matching_cluster_ids:
                cluster_ids = matching_cluster_ids
    snapshot = client.snapshot(
        node_limit=node_limit,
        edge_limit=edge_limit,
        label_keywords=label_keywords,
        cluster_ids=cluster_ids,
    )

    nodes = [
        Node(
            node_id=node["node_id"],
            label=node["label"],
            mass=node["mass"],
            activation=node["activation"],
            state=MemoryState(node["state"]),
            cluster_id=node.get("cluster_id") or None,
            embedding=node.get("embedding"),
            position=node.get("position", [0.0, 0.0, 0.0]),
            velocity=node.get("velocity", [0.0, 0.0, 0.0]),
            attention_weight=node.get("attention_weight", 0.0),
            created_at=node.get("created_at") or Node(node_id="tmp", label="tmp").created_at,
            metadata=node.get("metadata", {}),
        )
        for node in snapshot["nodes"]
    ]
    edges = [
        Edge(
            src_id=edge["src_id"],
            dst_id=edge["dst_id"],
            relation=edge.get("relation", "relates"),
            weight=edge["weight"],
            metadata=edge.get("metadata", {}),
        )
        for edge in snapshot["edges"]
    ]

    # Cognition graph: optionally include concepts that appear in waves whose label matches the query
    if live and terms:
        try:
            waves = client.list_waves(limit=100)
            matching_wave_ids = [
                w.wave_id for w in waves
                if any(t in w.label.lower() for t in terms)
            ]
            wave_concept_ids: set[str] = set()
            for wid in matching_wave_ids[:20]:
                for e in client.list_in_wave_edges(wave_id=wid, limit=500):
                    wave_concept_ids.add(e.src_id)
            if wave_concept_ids:
                extra_nodes = client.get_nodes_by_ids(list(wave_concept_ids))
                existing_ids = {n.node_id for n in nodes}
                for n in extra_nodes:
                    if n.node_id not in existing_ids:
                        nodes.append(n)
                        existing_ids.add(n.node_id)
                extra_edges = client.list_edges_between(existing_ids, limit=edge_limit)
                existing_edge_pairs = {(e.src_id, e.dst_id) for e in edges}
                for e in extra_edges:
                    if (e.src_id, e.dst_id) not in existing_edge_pairs:
                        edges.append(e)
                        existing_edge_pairs.add((e.src_id, e.dst_id))
        except Exception:
            pass
    direct_matches: list[Node] = []
    if label_keywords and nodes:
        direct_matches = list(nodes)

    # Fallback: filter by term match (dry-run or no keyword path)
    matching_nodes = [
        node
        for node in nodes
        if any(term in node.label.lower() for term in terms)
    ] if terms else []
    if not direct_matches and matching_nodes:
        direct_matches = matching_nodes

    if direct_matches:
        contextual_nodes, contextual_edges, seed_ids = _expand_contextual_nodes(
            client,
            direct_matches,
            nodes,
            edges,
            node_limit=node_limit,
            edge_limit=edge_limit,
        )
        final_nodes, final_edges = _gravity_recontextualize(
            client,
            contextual_nodes,
            contextual_edges,
            nodes,
            seed_ids,
            node_limit=node_limit,
            edge_limit=edge_limit,
        )
        client.close()
        return final_nodes, final_edges

    # Last resort: top by activation/mass
    ranked_nodes = sorted(
        nodes,
        key=lambda node: (node.activation, node.mass),
        reverse=True,
    )[: min(10, len(nodes))]
    selected_ids = {node.node_id for node in ranked_nodes}
    selected_edges = [
        edge for edge in edges if edge.src_id in selected_ids and edge.dst_id in selected_ids
    ]
    client.close()
    return ranked_nodes, selected_edges


def run_reasoning_loop(query: str, config_root: Path, live: bool = False) -> ReasoningResponse:
    reasoning_config = load_yaml_config(config_root / "configs" / "reasoning.yaml")["reasoning"]
    cache = CacheAdapter(config_root / "configs" / "reasoning.yaml")
    cache_key = f"query::{live}::{query.strip().lower()}"

    with query_latency_seconds.time():
        cached = cache.get(cache_key)
        if cached:
            cached_tension = TensionResult(**cached["tension"])
            # Keep gauges in sync even on cache hits.
            tension_score.set(cached_tension.score)
            graph_node_count.set(cached["graph_context"].get("nodes", 0))
            graph_edge_count.set(cached["graph_context"].get("edges", 0))
            return ReasoningResponse(
                query=cached["query"],
                activated_nodes=cached["activated_nodes"],
                hypotheses=[Hypothesis(**item) for item in cached["hypotheses"]],
                tension=cached_tension,
                graph_context=cached["graph_context"],
            )

        extractor = TripleExtractor(config_root / "configs" / "llm.yaml")
        extract_result = extractor.extract(query)
        activated = activate_from_query(query, extract_result.triples)

        # Memory-first retrieval: only expand the search terms if the graph does not
        # already contain a tangible local match for the query.
        graph_nodes, graph_edges = retrieve_graph_context(query, config_root, live=live)
        if not graph_nodes:
            seed_terms = list(_query_terms(query)) + extractor.suggest_search_terms(query, max_terms=10)
            graph_nodes, graph_edges = retrieve_graph_context(
                query,
                config_root,
                live=live,
                extra_keywords=seed_terms if live else seed_terms,
            )
        terms = _query_terms(query)
        # Only add graph labels that actually match the query (avoid flooding with unrelated cluster concepts)
        graph_activations = [
            node.label for node in graph_nodes
            if any(t in node.label.lower() for t in terms)
        ]
        activated = sorted(set(activated + graph_activations))

        # Build tension over a bounded set so score is meaningful (prefer nodes that have edges)
        edge_endpoint_labels = set()
        for edge in graph_edges:
            for node in graph_nodes:
                if node.node_id == edge.src_id:
                    edge_endpoint_labels.add(node.label)
                if node.node_id == edge.dst_id:
                    edge_endpoint_labels.add(node.label)
        tension_cap = 50
        if len(activated) > tension_cap:
            # Prefer: query-matching labels that are edge endpoints, then any edge endpoint, then query-matching
            in_graph = [a for a in activated if a in edge_endpoint_labels]
            in_graph = in_graph[:tension_cap]
            remaining = tension_cap - len(in_graph)
            if remaining > 0:
                others = [a for a in activated if a not in edge_endpoint_labels][:remaining]
                tension_activated = sorted(set(in_graph + others))
            else:
                tension_activated = in_graph
        else:
            tension_activated = activated

        positions = {
            name: np.asarray([idx + 1.0, idx * 0.5 + 1.0, 0.25], dtype=np.float32)
            for idx, name in enumerate(tension_activated)
        }
        expected_distances = {}
        for index in range(max(0, len(tension_activated) - 1)):
            expected_distances[(tension_activated[index], tension_activated[index + 1])] = 1.0
        for edge in graph_edges:
            src_label = next((node.label for node in graph_nodes if node.node_id == edge.src_id), None)
            dst_label = next((node.label for node in graph_nodes if node.node_id == edge.dst_id), None)
            if src_label and dst_label and src_label in positions and dst_label in positions:
                expected_distances[(src_label, dst_label)] = max(0.25, 1.0 / max(edge.weight, 0.01))
        tension = compute_tension(positions, expected_distances)
        hypotheses = generate_hypotheses(
            tension,
            reasoning_config["hypothesis_count"],
        )

        response = ReasoningResponse(
            query=query,
            activated_nodes=activated,
            hypotheses=hypotheses,
            tension=tension,
            graph_context={"nodes": len(graph_nodes), "edges": len(graph_edges)},
        )
        cache.set(
            cache_key,
            {
                "query": query,
                "activated_nodes": response.activated_nodes,
                "hypotheses": [asdict(hypothesis) for hypothesis in response.hypotheses],
                "tension": {
                    "score": response.tension.score,
                    "high_tension_pairs": response.tension.high_tension_pairs,
                },
                "graph_context": response.graph_context,
            },
        )

    # Update Prometheus gauges outside the timer context to reflect the latest state.
    tension_score.set(response.tension.score)
    graph_node_count.set(response.graph_context.get("nodes", 0))
    graph_edge_count.set(response.graph_context.get("edges", 0))

    # Persist reasoning episode to graph when live: one wave per query, in_wave edges to activated concepts
    if live and graph_nodes and hypotheses:
        try:
            persist_client = NebulaGraphClient(
                config_root / "configs" / "graph.yaml",
                dry_run_override=False,
            )
            wave_id = "reasoning_" + hashlib.sha256(query.strip().lower().encode()).hexdigest()[:14]
            wave = Wave(
                wave_id=wave_id,
                label=(query[:80].replace("\n", " ").strip() or "query"),
                source=WAVE_SOURCE_REASONING,
                intensity=float(len(hypotheses)),
                coherence=0.0,
                tension=tension.score,
                source_chunk_id=cache_key or wave_id,
            )
            persist_client.insert_waves([wave])
            activated_labels = set(activated)
            in_wave_edges = [
                Edge(
                    src_id=node.node_id,
                    dst_id=wave_id,
                    relation=EDGE_IN_WAVE,
                    weight=0.5,
                    metadata={"source": "reasoning", "query": query[:64]},
                )
                for node in graph_nodes
                if node.label in activated_labels
            ]
            if in_wave_edges:
                persist_client.insert_edges(in_wave_edges)
            # Post-wave learning: reweight relates edges for high-tension (contradiction) pairs
            label_to_node_ids: dict[str, list[str]] = {}
            for node in graph_nodes:
                label_to_node_ids.setdefault(node.label, []).append(node.node_id)
            edges_to_reweight: list[Edge] = []
            for src_label, dst_label, _delta in tension.high_tension_pairs:
                src_ids = label_to_node_ids.get(src_label, [])
                dst_ids = label_to_node_ids.get(dst_label, [])
                for e in graph_edges:
                    if e.relation != "relates":
                        continue
                    if e.src_id in src_ids and e.dst_id in dst_ids:
                        new_weight = max(0.0, float(e.weight) - REWEIGHT_CONFLICT_DELTA)
                        edges_to_reweight.append(
                            Edge(src_id=e.src_id, dst_id=e.dst_id, relation="relates", weight=new_weight, metadata=e.metadata)
                        )
                        break
                    if e.src_id in dst_ids and e.dst_id in src_ids:
                        new_weight = max(0.0, float(e.weight) - REWEIGHT_CONFLICT_DELTA)
                        edges_to_reweight.append(
                            Edge(src_id=e.src_id, dst_id=e.dst_id, relation="relates", weight=new_weight, metadata=e.metadata)
                        )
                        break
            if edges_to_reweight:
                persist_client.update_edges(edges_to_reweight)
            persist_client.close()
        except Exception as e:
            logger.exception("Failed to persist reasoning wave or reweight edges: %s", e)

    return response


def preload_graph_context(config_root: Path, live: bool = False) -> dict[str, int]:
    client = NebulaGraphClient(
        config_root / "configs" / "graph.yaml",
        dry_run_override=not live if live else None,
    )
    snapshot = client.snapshot()
    client.close()
    return {"nodes": len(snapshot["nodes"]), "edges": len(snapshot["edges"])}
