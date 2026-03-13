"""
Stage 7: Knowledge explorer — query → retrieve subgraph → output nodes/edges (e.g. for viz or export).
Dry-run by default. Writes JSON to stdout or --output file.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description="GOAT-TS knowledge explorer: query → subgraph JSON.")
    parser.add_argument("query", type=str, nargs="?", default="", help="Query string.")
    parser.add_argument("--live", action="store_true", help="Use live graph.")
    parser.add_argument("--output", type=Path, default=None, help="Write JSON here (default stdout).")
    parser.add_argument("--limit-nodes", type=int, default=100, help="Max nodes in context.")
    args = parser.parse_args()

    query = args.query or "knowledge graph"
    from src.reasoning.loop import run_reasoning_loop, retrieve_graph_context

    live = args.live
    nodes, edges = retrieve_graph_context(
        query, ROOT, live=live,
        node_limit=args.limit_nodes,
        edge_limit=500,
    )
    # Also run full reasoning for hypotheses
    response = run_reasoning_loop(query, ROOT, live=live)
    payload = {
        "query": query,
        "nodes": [{"node_id": n.node_id, "label": n.label, "activation": n.activation} for n in nodes[:args.limit_nodes]],
        "edges": [{"src_id": e.src_id, "dst_id": e.dst_id, "weight": e.weight} for e in edges[:500]],
        "tension_score": response.tension.score,
        "hypotheses": [{"prompt": h.prompt} for h in response.hypotheses[:5]],
    }
    text = json.dumps(payload, indent=2, default=str)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
        print(f"Wrote {args.output}", file=sys.stderr)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
