from __future__ import annotations

import argparse
import uuid
from pathlib import Path
from typing import Iterable

from tqdm import tqdm

from src.graph.client import NebulaGraphClient
from src.graph.cognition import EDGE_IN_WAVE, WAVE_SOURCE_INGESTION
from src.graph.models import Edge, MemoryState, Node, Triple, Wave
from src.ingestion.llm_extract import TripleExtractor

# Cluster/topic nodes use this label prefix so retrieval can find them.
CLUSTER_LABEL_PREFIX = "topic: "

# UUIDv5 namespace for GOAT node IDs (collision avoidance per spec).
GOAT_NAMESPACE = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")


def stable_node_id(seed: str) -> str:
    """Deterministic node ID via UUIDv5 (spec: collision avoidance)."""
    return str(uuid.uuid5(GOAT_NAMESPACE, seed.strip().lower().encode("utf-8"))).replace("-", "")[:32]


def _triples_to_graph_for_chunk(
    triples: list[Triple],
    topic_id: str,
    topic_label: str,
) -> tuple[Node, list[Node], list[Edge], Wave, list[Edge]]:
    """Build one cluster node, concept nodes, relates edges, one cognition wave, and in_wave edges for a chunk."""
    cluster_node_id = stable_node_id("cluster:" + topic_id)
    cluster_node = Node(
        node_id=cluster_node_id,
        label=CLUSTER_LABEL_PREFIX + topic_label[:60].replace("\n", " ").strip(),
        activation=1.0,
        mass=1.0,
        state=MemoryState.ACTIVE,
        cluster_id="",
        metadata={"source": "extractor", "type": "cluster"},
    )
    wave_id = stable_node_id("wave:" + topic_id)
    wave = Wave(
        wave_id=wave_id,
        label=topic_label[:80].replace("\n", " ").strip() or topic_id,
        source=WAVE_SOURCE_INGESTION,
        intensity=float(len(triples)),
        coherence=0.0,
        tension=0.0,
        source_chunk_id=topic_id,
    )
    node_map: dict[str, Node] = {}
    edges: list[Edge] = []
    in_wave_edges: list[Edge] = []

    for triple in triples:
        # Context-scoped: same label in different chunks = different node
        src_id = stable_node_id(topic_id + ":" + triple.subject)
        dst_id = stable_node_id(topic_id + ":" + triple.object)
        node_map.setdefault(
            src_id,
            Node(
                node_id=src_id,
                label=triple.subject,
                activation=1.0,
                mass=1.0,
                state=MemoryState.ACTIVE,
                cluster_id=cluster_node_id,
                metadata={"source": "extractor"},
            ),
        )
        node_map.setdefault(
            dst_id,
            Node(
                node_id=dst_id,
                label=triple.object,
                activation=0.5,
                mass=0.75,
                state=MemoryState.DORMANT,
                cluster_id=cluster_node_id,
                metadata={"source": "extractor"},
            ),
        )
        edges.append(
            Edge(
                src_id=src_id,
                dst_id=dst_id,
                relation="relates",
                weight=triple.confidence,
                metadata={"relation": triple.relation, "incomplete": False},
            )
        )

    # One concept -> cluster edge per concept (belongs to this topic)
    for nid in node_map:
        edges.append(
            Edge(
                src_id=nid,
                dst_id=cluster_node_id,
                relation="relates",
                weight=0.5,
                metadata={"relation": "belongs_to"},
            )
        )
        # Cognition graph: concept participates in this wave (provenance)
        in_wave_edges.append(
            Edge(
                src_id=nid,
                dst_id=wave_id,
                relation=EDGE_IN_WAVE,
                weight=0.5,
                metadata={"source_chunk_id": topic_id},
            )
        )

    return cluster_node, list(node_map.values()), edges, wave, in_wave_edges


def _prune_excess_nodes(
    concept_nodes: list[Node],
    edges: list[Edge],
    max_per_label: int = 10,
) -> tuple[list[Node], list[Edge]]:
    """Keep at most max_per_label nodes per label (by edge degree); drop the rest and their edges."""
    from collections import defaultdict

    # Degree per node_id (count of incident edges)
    degree: dict[str, int] = defaultdict(int)
    for e in edges:
        degree[e.src_id] += 1
        degree[e.dst_id] += 1

    # Group concept nodes by label (same word in different contexts)
    by_label: dict[str, list[Node]] = defaultdict(list)
    for n in concept_nodes:
        by_label[n.label].append(n)

    keep_ids: set[str] = set()
    for label, nodes in by_label.items():
        if len(nodes) <= max_per_label:
            keep_ids.update(n.node_id for n in nodes)
        else:
            # Keep top max_per_label by degree
            sorted_nodes = sorted(nodes, key=lambda n: degree[n.node_id], reverse=True)
            for n in sorted_nodes[:max_per_label]:
                keep_ids.add(n.node_id)

    kept_nodes = [n for n in concept_nodes if n.node_id in keep_ids]
    kept_edges = [
        e for e in edges
        if e.src_id in keep_ids and e.dst_id in keep_ids
    ]
    return kept_nodes, kept_edges


def triples_to_graph(triples: Iterable[Triple]) -> tuple[list[Node], list[Edge]]:
    """Legacy: one global node per label (no clusters). Kept for tests."""
    node_map: dict[str, Node] = {}
    edges: list[Edge] = []
    for triple in triples:
        src_id = stable_node_id(triple.subject)
        dst_id = stable_node_id(triple.object)
        node_map.setdefault(
            src_id,
            Node(
                node_id=src_id,
                label=triple.subject,
                activation=1.0,
                mass=1.0,
                state=MemoryState.ACTIVE,
                metadata={"source": "extractor"},
            ),
        )
        node_map.setdefault(
            dst_id,
            Node(
                node_id=dst_id,
                label=triple.object,
                activation=0.5,
                mass=0.75,
                state=MemoryState.DORMANT,
                metadata={"source": "extractor"},
            ),
        )
        edges.append(
            Edge(
                src_id=src_id,
                dst_id=dst_id,
                relation="relates",
                weight=triple.confidence,
                metadata={"relation": triple.relation, "incomplete": False},
            )
        )
    return list(node_map.values()), edges


def extract_from_texts(
    texts: Iterable[str],
    config_root: Path,
    *,
    use_clusters: bool = True,
    max_nodes_per_label: int = 10,
    llm_config_path: Path | None = None,
) -> tuple[list[Node], list[Edge], list[Wave], list[Edge]]:
    """Returns (concept/cluster nodes, relates edges, waves, in_wave edges).

    Extractor: TripleExtractor from configs/llm.yaml. If enable_model_inference is true,
    uses Hugging Face text2text-generation (e.g. google/flan-t5-base); otherwise
    regex fallback (subject is/has/uses object). Set --config or config_root for custom path.
    """
    config_path = llm_config_path or (config_root / "configs" / "llm.yaml")
    extractor = TripleExtractor(config_path)
    text_list = list(texts)
    cluster_nodes: list[Node] = []
    concept_nodes: list[Node] = []
    all_edges: list[Edge] = []
    waves: list[Wave] = []
    in_wave_edges: list[Edge] = []

    for idx, chunk in enumerate(tqdm(text_list, unit="chunks", desc="Extracting triples")):
        result = extractor.extract(chunk)
        if not result.triples:
            continue
        topic_id = f"doc_{idx}"
        topic_label = chunk[:80].replace("\n", " ").strip() or topic_id
        if use_clusters:
            cluster_node, nodes, edges, wave, chunk_in_wave = _triples_to_graph_for_chunk(
                result.triples, topic_id, topic_label
            )
            cluster_nodes.append(cluster_node)
            concept_nodes.extend(nodes)
            all_edges.extend(edges)
            waves.append(wave)
            in_wave_edges.extend(chunk_in_wave)
        else:
            cn, ce = triples_to_graph(result.triples)
            concept_nodes.extend(cn)
            all_edges.extend(ce)

    if use_clusters and concept_nodes:
        concept_nodes, all_edges = _prune_excess_nodes(
            concept_nodes, all_edges, max_per_label=max_nodes_per_label
        )
        keep_ids = {n.node_id for n in concept_nodes}
        in_wave_edges = [e for e in in_wave_edges if e.src_id in keep_ids]
        nodes_out = cluster_nodes + concept_nodes
    else:
        nodes_out = concept_nodes

    return nodes_out, all_edges, waves, in_wave_edges


def load_into_graph(
    texts: Iterable[str],
    config_root: Path,
    *,
    live: bool = False,
    use_clusters: bool = True,
    max_nodes_per_label: int = 10,
    llm_config_path: Path | None = None,
    global_merge: bool = False,
    merge_threshold: float = 0.8,
) -> dict[str, int]:
    nodes, edges, waves, in_wave_edges = extract_from_texts(
        texts, config_root,
        use_clusters=use_clusters,
        max_nodes_per_label=max_nodes_per_label,
        llm_config_path=llm_config_path,
    )
    if global_merge and nodes:
        from src.graph.cluster_merge import global_concept_merge
        config_path = config_root / "configs" / "graph.yaml"
        all_edges = edges + in_wave_edges
        nodes, all_edges = global_concept_merge(
            nodes, all_edges,
            similarity_threshold=merge_threshold,
            config_path=config_path if config_path.exists() else None,
        )
        # Split back: in_wave has dst_id in wave_ids
        wave_ids = {w.wave_id for w in waves}
        edges = [e for e in all_edges if e.dst_id not in wave_ids]
        in_wave_edges = [e for e in all_edges if e.dst_id in wave_ids]
    client = NebulaGraphClient(
        config_root / "configs" / "graph.yaml",
        dry_run_override=False if live else None,
    )
    progress_interval = max(1, min(2000, len(nodes) // 20)) if nodes else 1000
    with tqdm(total=len(nodes), unit="nodes", desc="Inserting nodes") as pbar:
        def node_progress(current: int, total: int) -> None:
            pbar.n = current
            pbar.refresh()
        client.insert_nodes(nodes, on_progress=node_progress, progress_interval=progress_interval)
    if waves:
        progress_interval = max(1, min(500, len(waves) // 10)) if waves else 500
        with tqdm(total=len(waves), unit="waves", desc="Inserting waves") as pbar:
            def wave_progress(current: int, total: int) -> None:
                pbar.n = current
                pbar.refresh()
            client.insert_waves(waves, on_progress=wave_progress, progress_interval=progress_interval)
    all_edges = edges + in_wave_edges
    progress_interval = max(1, min(2000, len(all_edges) // 20)) if all_edges else 1000
    with tqdm(total=len(all_edges), unit="edges", desc="Inserting edges") as pbar:
        def edge_progress(current: int, total: int) -> None:
            pbar.n = current
            pbar.refresh()
        client.insert_edges(all_edges, on_progress=edge_progress, progress_interval=progress_interval)
    client.close()
    return {"nodes": len(nodes), "edges": len(edges), "waves": len(waves), "in_wave_edges": len(in_wave_edges)}


def _read_texts_from_path(input_path: Path) -> list[str]:
    """Load text chunks from a .txt file or from parquet (Spark text output has 'value' column)."""
    input_path = input_path.resolve()
    is_parquet = (
        input_path.suffix.lower() == ".parquet"
        or (input_path.is_dir() and any(input_path.glob("*.parquet")))
    )
    if is_parquet:
        try:
            import pyarrow.parquet as pq
        except ImportError:
            raise SystemExit("Reading parquet requires pyarrow. Install with: pip install pyarrow")
        table = pq.read_table(input_path)
        if "value" not in table.column_names:
            raise SystemExit("Parquet must have a 'value' column (e.g. from spark.read.text()).")
        return [row.as_py().strip() for row in table.column("value") if row.as_py() and row.as_py().strip()]
    # Plain text: one chunk per line
    return [
        line.strip()
        for line in input_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a local extraction pipeline.")
    parser.add_argument(
        "--input-path",
        required=True,
        help="Text file (one chunk per line) or parquet file/dir (with 'value' column).",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Insert extracted nodes/edges into live NebulaGraph.",
    )
    parser.add_argument(
        "--no-clusters",
        action="store_true",
        help="Disable cluster/topic nodes and context-scoped concepts (flat graph, one node per label).",
    )
    parser.add_argument(
        "--max-nodes-per-label",
        type=int,
        default=10,
        help="Max concept nodes to keep per label when pruning (default 10).",
    )
    parser.add_argument(
        "--config",
        help="Path to LLM/extraction config (default: configs/llm.yaml). Extractor uses enable_model_inference and model_name.",
    )
    parser.add_argument(
        "--global-merge",
        action="store_true",
        help="Run global concept merge (FAISS similarity > threshold) before inserting into graph.",
    )
    parser.add_argument(
        "--merge-threshold",
        type=float,
        default=0.8,
        help="Cosine similarity threshold for global merge (default 0.8).",
    )
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[2]
    llm_config = Path(args.config) if args.config else None
    input_path = Path(args.input_path)
    if not input_path.exists():
        raise SystemExit(f"Input path does not exist: {input_path}")
    texts = _read_texts_from_path(input_path)
    if not texts:
        raise SystemExit("No text chunks found.")
    stats = load_into_graph(
        texts, root,
        live=args.live,
        use_clusters=not args.no_clusters,
        max_nodes_per_label=args.max_nodes_per_label,
        llm_config_path=llm_config,
        global_merge=args.global_merge,
        merge_threshold=args.merge_threshold,
    )
    print(stats)


if __name__ == "__main__":
    main()
