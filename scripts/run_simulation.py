from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.simulation.loop import run_from_graph


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a simulation step from graph state.")
    parser.add_argument(
        "--live",
        action="store_true",
        help="Read nodes and edges from the live NebulaGraph instance.",
    )
    parser.add_argument("--node-limit", type=int, default=250)
    parser.add_argument("--edge-limit", type=int, default=2000)
    args = parser.parse_args()

    result = run_from_graph(
        ROOT,
        live=args.live,
        node_limit=args.node_limit,
        edge_limit=args.edge_limit,
    )
    print(result)


if __name__ == "__main__":
    main()
