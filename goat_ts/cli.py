"""Command-line entry points for the v0.1 kernel."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

from goat_ts import __version__
from goat_ts.core.graph import InMemoryGraph
from goat_ts.core.ids import deterministic_id, wave_id
from goat_ts.core.models import Receipt, Wave
from goat_ts.engine.activation import spread_activation
from goat_ts.engine.memory import transition_memory
from goat_ts.engine.tension import score_tension
from goat_ts.ingest.parser import parse_text
from goat_ts.receipts.writer import write_receipt


def run_demo(input_path: str | Path, output_path: str | Path) -> Receipt:
    source = Path(input_path).as_posix()
    content = Path(input_path).read_text(encoding="utf-8")
    content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
    wave = Wave(id=wave_id(source, content), source=source, content_hash=content_hash)
    candidates, repairs = parse_text(content)

    graph = InMemoryGraph()
    for claim in candidates:
        graph.insert_claim(claim, wave)

    seeds = (graph.sorted_nodes()[0].id,) if graph.nodes else ()
    activation = spread_activation(graph, seeds)
    memory = transition_memory(graph)
    tension = score_tension(graph)
    receipt = Receipt(
        id=deterministic_id("receipt", "demo", wave.id),
        version=__version__,
        operation="demo",
        input={"path": source, "sha256": content_hash},
        waves=(wave,),
        candidates=tuple(sorted(candidates, key=lambda item: item.id)),
        nodes=graph.sorted_nodes(),
        edges=graph.sorted_edges(),
        repair_targets=tuple(sorted(repairs, key=lambda item: item.id)),
        activation=activation,
        memory=memory,
        tension=tension,
    )
    write_receipt(receipt, output_path)
    return receipt


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="goat-ts")
    subcommands = parser.add_subparsers(dest="command", required=True)
    demo = subcommands.add_parser("demo", help="run the deterministic v0.1 demo")
    demo.add_argument("--input", required=True)
    demo.add_argument("--out", required=True)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "demo":
        receipt = run_demo(args.input, args.out)
        print(f"wrote {args.out} ({receipt.id})")


if __name__ == "__main__":
    main()
