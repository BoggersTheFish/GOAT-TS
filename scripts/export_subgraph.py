"""
Export a concept-centered subgraph to JSON and/or a PNG plot. Use for debug and demos.

Usage:
  python scripts/export_subgraph.py --concept "France" [--hops 2] [--live] [--output out.json] [--plot out.png]
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


def build_subgraph(client: NebulaGraphClient, concept: str, hops: int, node_limit: int, edge_limit: int) -> dict:
    """Get subgraph: nodes matching concept + neighbors up to hops. Returns {nodes, edges} as list of dicts."""
    snap = client.snapshot(
        node_limit=node_limit,
        edge_limit=edge_limit,
        label_keywords=[concept] if concept else None,
    )
    nodes = snap.get("nodes", [])
    edges = snap.get("edges", [])
    if hops <= 1 or not nodes:
        return {"nodes": nodes, "edges": edges}

    node_ids = {n["node_id"] for n in nodes}
    for _ in range(hops - 1):
        next_ids = set()
        for nid in node_ids:
            try:
                for neighbor in client.neighbors(nid):
                    next_ids.add(neighbor)
            except Exception:
                pass
        node_ids |= next_ids
        if not next_ids:
            break
    # Re-fetch edges between this set (induced subgraph)
    if node_ids:
        edge_list = client.list_edges_between(list(node_ids), limit=edge_limit)
        edges = [{"src_id": e.src_id, "dst_id": e.dst_id, "weight": e.weight} for e in edge_list]
        node_id_list = list(node_ids)
        nodes_fetched = client.get_nodes_by_ids(node_id_list)
        nodes = [
            {"node_id": n.node_id, "label": n.label, "mass": n.mass, "activation": n.activation}
            for n in nodes_fetched if n
        ]
    return {"nodes": nodes, "edges": edges}


def export_subgraph_to_dot(data: dict, dot_path: Path) -> None:
    """Write subgraph to a Graphviz .dot file for interpretability. data = {nodes, edges}."""
    lines = ["digraph G {", "  rankdir=LR;", "  node [shape=circle];"]
    for n in data.get("nodes", []):
        nid = n.get("node_id", "")
        label = (n.get("label") or nid).replace('"', '\\"')[:40]
        lines.append(f'  "{nid}" [label="{label}"];')
    for e in data.get("edges", []):
        src = e.get("src_id", "")
        dst = e.get("dst_id", "")
        w = e.get("weight", 1.0)
        lines.append(f'  "{src}" -> "{dst}" [weight={w:.2f}];')
    lines.append("}")
    dot_path = Path(dot_path)
    dot_path.parent.mkdir(parents=True, exist_ok=True)
    dot_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Export subgraph around a concept to JSON and/or PNG.")
    parser.add_argument("--concept", required=True, help="Concept label (or substring) to center the subgraph.")
    parser.add_argument("--hops", type=int, default=1, help="Neighbor hops (default 1).")
    parser.add_argument("--live", action="store_true", help="Query live NebulaGraph.")
    parser.add_argument("--output", help="Write JSON to this path.")
    parser.add_argument("--plot", help="Write PNG to this path (requires matplotlib).")
    parser.add_argument("--dot", help="Write Graphviz .dot to this path (interpretability).")
    parser.add_argument("--node-limit", type=int, default=500, help="Max nodes (default 500).")
    parser.add_argument("--edge-limit", type=int, default=2000, help="Max edges (default 2000).")
    args = parser.parse_args()

    client = NebulaGraphClient(
        ROOT / "configs" / "graph.yaml",
        dry_run_override=not args.live if args.live else None,
    )
    try:
        data = build_subgraph(
            client,
            concept=args.concept,
            hops=args.hops,
            node_limit=args.node_limit,
            edge_limit=args.edge_limit,
        )
    finally:
        client.close()

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        print(f"Wrote {len(data['nodes'])} nodes, {len(data['edges'])} edges to {out_path}")

    if args.dot:
        export_subgraph_to_dot(data, Path(args.dot))
        print(f"Wrote Graphviz .dot to {args.dot}")

    if args.plot:
        try:
            import networkx as nx
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
        except ImportError as e:
            print("Plot requires networkx and matplotlib: pip install networkx matplotlib", file=sys.stderr)
            sys.exit(1)
        G = nx.Graph()
        for n in data["nodes"]:
            G.add_node(n["node_id"], label=n.get("label", n["node_id"]))
        for e in data["edges"]:
            G.add_edge(e["src_id"], e["dst_id"], weight=e.get("weight", 1.0))
        if G.order() == 0:
            print("No nodes to plot.")
            return
        pos = nx.spring_layout(G, seed=42, k=0.5)
        labels = {n: G.nodes[n].get("label", n)[:12] for n in G}
        plt.figure(figsize=(10, 8))
        nx.draw(G, pos, labels=labels, with_labels=True, font_size=6, node_size=80)
        plot_path = Path(args.plot)
        plot_path.parent.mkdir(parents=True, exist_ok=True)
        plt.savefig(plot_path, dpi=120)
        plt.close()
        print(f"Saved plot to {plot_path}")

    if not args.output and not args.plot:
        print(json.dumps(data, indent=2))


if __name__ == "__main__":
    main()
