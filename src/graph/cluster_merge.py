"""
Global concept merging: find nodes with embedding similarity > threshold across
clusters, merge (combine mass, average activations, union edges). Uses
EmbeddingVectorIndex (FAISS) for similarity; embeddings from node metadata or
SentenceTransformer on node label. Removes per-chunk cluster fragmentation
when used as global cluster resolver during ingestion.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import numpy as np

from src.graph.models import Edge, Node
from src.graph.vector_index import EmbeddingVectorIndex

logger = logging.getLogger(__name__)

# Default similarity threshold for merging (spec: > 0.8)
DEFAULT_MERGE_THRESHOLD = 0.8
EMBEDDING_DIM = 384  # all-MiniLM-L6-v2


def _get_embedder(model_name: str = "all-MiniLM-L6-v2"):
    try:
        from sentence_transformers import SentenceTransformer
        return SentenceTransformer(model_name)
    except ImportError as e:
        raise RuntimeError(
            "sentence-transformers required for cluster merge. pip install sentence-transformers"
        ) from e


def _embed_node(node: Node, embedder) -> np.ndarray:
    """Return embedding for node from metadata or by encoding label."""
    if node.embedding is not None and len(node.embedding) == EMBEDDING_DIM:
        return np.asarray(node.embedding, dtype=np.float32)
    vec = embedder.encode(node.label, normalize_embeddings=True)
    return np.asarray(vec, dtype=np.float32)


def global_concept_merge(
    nodes: list[Node],
    edges: list[Edge],
    *,
    similarity_threshold: float = DEFAULT_MERGE_THRESHOLD,
    embedding_model_name: str = "all-MiniLM-L6-v2",
    config_path: Optional[Path] = None,
) -> tuple[list[Node], list[Edge]]:
    """
    Find concept nodes with cosine similarity > threshold (on embeddings),
    merge them: combine mass, average activations, union edges. Returns
    (merged_nodes, merged_edges). Cluster/topic nodes are not merged;
    only concept nodes (no cluster label prefix) are considered.
    """
    from src.graph.cognition import CLUSTER_LABEL_PREFIX
    from src.utils import load_yaml_config

    concept_nodes = [n for n in nodes if not (n.label or "").strip().startswith(CLUSTER_LABEL_PREFIX)]
    cluster_and_other = [n for n in nodes if (n.label or "").strip().startswith(CLUSTER_LABEL_PREFIX)]
    if not concept_nodes:
        return nodes, edges

    if config_path and config_path.exists():
        try:
            cfg = load_yaml_config(config_path)
            graph_cfg = cfg.get("graph", {})
            embedding_model_name = graph_cfg.get("embedding_model", embedding_model_name)
        except Exception:
            pass

    embedder = _get_embedder(embedding_model_name)
    embeddings = np.array([_embed_node(n, embedder) for n in concept_nodes], dtype=np.float32)
    if embeddings.shape[1] != EMBEDDING_DIM:
        # Resize or use first 384 if model differs
        if embeddings.shape[1] > EMBEDDING_DIM:
            embeddings = embeddings[:, :EMBEDDING_DIM]
        else:
            pad = np.zeros((len(concept_nodes), EMBEDDING_DIM - embeddings.shape[1]), dtype=np.float32)
            embeddings = np.hstack([embeddings, pad])

    index = EmbeddingVectorIndex(dimension=EMBEDDING_DIM)
    node_ids = [n.node_id for n in concept_nodes]
    index.add(node_ids, embeddings)

    pairs = index.find_similar_pairs(threshold=similarity_threshold, exclude_self=True)
    # Union-find: canonical id per equivalence class
    parent: dict[str, str] = {nid: nid for nid in node_ids}

    def find(x: str) -> str:
        if parent[x] != x:
            parent[x] = find(parent[x])
        return parent[x]

    for id_a, id_b, _ in pairs:
        ra, rb = find(id_a), find(id_b)
        if ra != rb:
            parent[ra] = rb

    # Each root -> min node_id in that class (canonical representative)
    roots: dict[str, str] = {}
    for nid in node_ids:
        r = find(nid)
        roots[r] = min(roots.get(r, nid), nid)
    canonical = {nid: roots[find(nid)] for nid in node_ids}

    # Build merged nodes: one per canonical id
    by_canonical: dict[str, list[Node]] = {}
    for n in concept_nodes:
        c = canonical[n.node_id]
        by_canonical.setdefault(c, []).append(n)
    merged_concepts: list[Node] = []
    for cid, group in by_canonical.items():
        if len(group) == 1:
            merged_concepts.append(group[0])
            continue
        # Combine mass, average activations; keep first node's id/label, merge metadata
        total_mass = sum(n.mass for n in group)
        avg_act = sum(n.activation for n in group) / len(group)
        first = group[0]
        merged_concepts.append(
            Node(
                node_id=first.node_id,
                label=first.label,
                mass=total_mass,
                activation=avg_act,
                state=first.state,
                cluster_id=first.cluster_id,
                embedding=first.embedding,
                position=first.position,
                velocity=first.velocity,
                metadata={**first.metadata, "merged_from": [n.node_id for n in group]},
            )
        )

    # Remap edges: replace any node id with its canonical
    def remap(e: Edge) -> Edge:
        src = canonical.get(e.src_id, e.src_id)
        dst = canonical.get(e.dst_id, e.dst_id)
        if src == dst:
            return None  # self-loop after merge, drop
        return Edge(src_id=src, dst_id=dst, relation=e.relation, weight=e.weight, metadata=dict(e.metadata))
    new_edges: list[Edge] = []
    seen_edges: set[tuple[str, str, str]] = set()
    for e in edges:
        r = remap(e)
        if r is None:
            continue
        key = (r.src_id, r.dst_id, r.relation)
        if key in seen_edges:
            continue
        seen_edges.add(key)
        new_edges.append(r)

    result_nodes = cluster_and_other + merged_concepts
    return result_nodes, new_edges
