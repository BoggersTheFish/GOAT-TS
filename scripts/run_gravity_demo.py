"""
Run N gravity simulation steps and optionally write positions to JSON and a 2D plot.
Uses the same physics as run_simulation.py but does not persist to the graph.
Useful for demos and debugging layout.

Usage:
  python scripts/run_gravity_demo.py [--live] [--iterations 100] [--output positions.json] [--plot layout.png]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.graph.client import NebulaGraphClient
from src.graph.models import Edge, MemoryState, Node
from src.simulation.gravity import build_state, compute_forces, update_positions


def _synthetic_snapshot() -> tuple[list[Node], list[Edge]]:
    """Minimal in-memory graph for demo when no DB is available."""
    nodes = [
        Node(node_id="a", label="Concept A", mass=1.0, activation=0.5, state=MemoryState.DORMANT, position=[0.0, 0.0, 0.0], velocity=[0.0, 0.0, 0.0]),
        Node(node_id="b", label="Concept B", mass=0.8, activation=0.3, state=MemoryState.DORMANT, position=[1.0, 0.0, 0.0], velocity=[0.0, 0.0, 0.0]),
        Node(node_id="c", label="Concept C", mass=0.9, activation=0.4, state=MemoryState.DORMANT, position=[0.5, 1.0, 0.0], velocity=[0.0, 0.0, 0.0]),
    ]
    edges = [
        Edge(src_id="a", dst_id="b", relation="relates", weight=0.8),
        Edge(src_id="b", dst_id="c", relation="relates", weight=0.6),
        Edge(src_id="a", dst_id="c", relation="relates", weight=0.4),
    ]
    return nodes, edges


def load_snapshot(config_root: Path, live: bool, node_limit: int, edge_limit: int) -> tuple[list[Node], list[Edge]]:
    """Load nodes and edges from graph (live or dry-run). If dry-run and empty, use synthetic snapshot."""
    client = NebulaGraphClient(
        config_root / "configs" / "graph.yaml",
        dry_run_override=not live if live else None,
    )
    try:
        snapshot = client.snapshot_induced_by_edges(edge_limit=edge_limit)
    finally:
        client.close()

    if not snapshot["nodes"] and not live:
        return _synthetic_snapshot()

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
            src_id=e["src_id"],
            dst_id=e["dst_id"],
            relation=e.get("relation", "relates"),
            weight=e.get("weight", 1.0),
            metadata=e.get("metadata", {}),
        )
        for e in snapshot["edges"]
    ]
    return nodes, edges


def run_n_steps(
    nodes: list[Node],
    edges: list[Edge],
    iterations: int,
    config_path: Path,
    step_size: float = 0.1,
) -> list[dict]:
    """Run N gravity steps and return list of {node_id, label, position} per final state."""
    state = build_state(nodes)
    sim_config_path = str(config_path)

    for _ in range(iterations):
        forces = compute_forces(state, edges=edges, config_path=sim_config_path)
        state = update_positions(state, forces, config_path=sim_config_path, step_size=step_size)

    return [
        {"node_id": state.node_ids[i], "label": nodes[i].label, "position": state.positions[i].tolist()}
        for i in range(len(state.node_ids))
    ]


def plot_2d(positions_data: list[dict], edges: list[Edge], node_id_to_idx: dict[str, int], out_path: Path) -> None:
    """Draw 2D layout (x, y) with nodes and edges, save to PNG."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import networkx as nx
    except ImportError as e:
        print("Plot requires networkx and matplotlib: pip install networkx matplotlib", file=sys.stderr)
        raise SystemExit(1) from e

    G = nx.Graph()
    for p in positions_data:
        G.add_node(p["node_id"], label=p.get("label", p["node_id"]), pos=(p["position"][0], p["position"][1]))
    for e in edges:
        if e.src_id in node_id_to_idx and e.dst_id in node_id_to_idx:
            G.add_edge(e.src_id, e.dst_id)

    if G.order() == 0:
        print("No nodes to plot.")
        return

    pos = {n: G.nodes[n]["pos"] for n in G}
    labels = {n: (G.nodes[n].get("label", n) or n)[:12] for n in G}
    plt.figure(figsize=(10, 8))
    nx.draw(G, pos, labels=labels, with_labels=True, font_size=6, node_size=80)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(out_path, dpi=120)
    plt.close()
    print(f"Saved plot to {out_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run N gravity steps and export positions (JSON) and/or 2D plot.")
    parser.add_argument("--live", action="store_true", help="Read graph from live NebulaGraph.")
    parser.add_argument("--iterations", type=int, default=100, help="Number of simulation steps (default 100).")
    parser.add_argument("--node-limit", type=int, default=250)
    parser.add_argument("--edge-limit", type=int, default=2000)
    parser.add_argument("--output", help="Write positions JSON to this path.")
    parser.add_argument("--plot", help="Write 2D layout PNG to this path.")
    args = parser.parse_args()

    config_path = ROOT / "configs" / "simulation.yaml"
    nodes, edges = load_snapshot(ROOT, args.live, args.node_limit, args.edge_limit)
    if not nodes:
        print("No nodes in snapshot. Use --live after ingestion or generate_sample_100k.py with --live first.")
        sys.exit(1)

    positions_data = run_n_steps(nodes, edges, args.iterations, config_path)
    node_id_to_idx = {n["node_id"]: i for i, n in enumerate(positions_data)}

    payload = {
        "iterations": args.iterations,
        "node_count": len(positions_data),
        "edge_count": len(edges),
        "nodes": positions_data,
    }

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"Wrote {len(positions_data)} positions to {out_path}")

    if args.plot:
        plot_2d(positions_data, edges, node_id_to_idx, Path(args.plot))

    if not args.output and not args.plot:
        print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
