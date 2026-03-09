"""
Print node/edge/wave counts for the graph. Use after --live ingestion to verify data.

Usage:
  python scripts/dump_graph_stats.py [--live]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.graph.client import NebulaGraphClient


def main() -> None:
    parser = argparse.ArgumentParser(description="Dump graph stats (nodes, edges, waves).")
    parser.add_argument("--live", action="store_true", help="Query live NebulaGraph.")
    parser.add_argument("--sample-limit", type=int, default=50000, help="Max items to count via list (default 50000).")
    args = parser.parse_args()

    client = NebulaGraphClient(
        ROOT / "configs" / "graph.yaml",
        dry_run_override=not args.live if args.live else None,
    )
    try:
        nodes = client.list_nodes(limit=args.sample_limit)
        waves = client.list_waves(limit=args.sample_limit)
        in_wave_edges = client.list_in_wave_edges(limit=args.sample_limit)
        # relates edges: use list_edges if available, else approximate from snapshot
        try:
            relates = client.list_edges(limit=args.sample_limit)
        except Exception:
            relates = []
            snap = client.snapshot_induced_by_edges(edge_limit=args.sample_limit)
            relates = snap.get("edges", [])

        n_node = len(nodes)
        n_wave = len(waves)
        n_in_wave = len(in_wave_edges)
        n_relates = len(relates) if isinstance(relates, list) else 0

        print("mode:", "live" if args.live else "dry-run")
        print("nodes (node tag):", n_node)
        print("waves (wave tag):", n_wave)
        print("edges (relates):", n_relates)
        print("edges (in_wave):", n_in_wave)
        if n_node or n_wave:
            print("(Counts are capped by --sample-limit; increase for full graph.)")
    finally:
        client.close()


if __name__ == "__main__":
    main()
