from __future__ import annotations

import argparse
import random
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tqdm import tqdm

from src.graph.client import NebulaGraphClient
from src.graph.models import Edge, MemoryState, Node


def build_sample_nodes(node_count: int) -> list[Node]:
    states = [MemoryState.ACTIVE, MemoryState.DORMANT, MemoryState.DEEP]
    return [
        Node(
            node_id=f"node-{idx:06d}",
            label=f"Concept {idx}",
            mass=1.0 + (idx % 10) * 0.1,
            activation=0.1 + (idx % 5) * 0.05,
            state=states[idx % len(states)],
            metadata={"domain": f"domain-{idx % 20}"},
        )
        for idx in range(node_count)
    ]


def build_sample_edges(node_count: int, edge_count: int) -> list[Edge]:
    random.seed(42)
    edges: list[Edge] = []
    for _ in range(edge_count):
        src = random.randrange(node_count)
        dst = random.randrange(node_count)
        if src == dst:
            continue
        edges.append(
            Edge(
                src_id=f"node-{src:06d}",
                dst_id=f"node-{dst:06d}",
                relation="relates",
                weight=round(random.uniform(0.1, 1.0), 3),
                metadata={"relation": "sample_link"},
            )
        )
    return edges


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a synthetic graph sample.")
    parser.add_argument("--node-count", type=int, default=100_000)
    parser.add_argument("--edge-count", type=int, default=250_000)
    parser.add_argument(
        "--live",
        action="store_true",
        help="Insert into a live NebulaGraph instance instead of dry-run mode.",
    )
    args = parser.parse_args()

    client = NebulaGraphClient(
        ROOT / "configs" / "graph.yaml",
        dry_run_override=not args.live if args.live else None,
    )
    nodes = build_sample_nodes(args.node_count)
    edges = build_sample_edges(args.node_count, args.edge_count)

    progress_interval = max(1, min(5000, len(nodes) // 20))
    with tqdm(total=len(nodes), unit="nodes", desc="Inserting nodes") as pbar:
        def node_progress(current: int, total: int) -> None:
            pbar.n = current
            pbar.refresh()
        client.insert_nodes(nodes, on_progress=node_progress, progress_interval=progress_interval)

    progress_interval = max(1, min(5000, len(edges) // 20))
    with tqdm(total=len(edges), unit="edges", desc="Inserting edges") as pbar:
        def edge_progress(current: int, total: int) -> None:
            pbar.n = current
            pbar.refresh()
        client.insert_edges(edges, on_progress=edge_progress, progress_interval=progress_interval)

    print(
        {
            "inserted_nodes": len(nodes),
            "inserted_edges": len(edges),
            "active_nodes": len(client.search_by_state("active")),
            "neighbors_of_first": client.neighbors("node-000000")[:10],
        }
    )
    client.close()


if __name__ == "__main__":
    main()
