"""
Stage 6: One-click demo — run cognition loop + optional reasoning in one go.
No Docker required when using --dry-run (default). Presets from configs/presets.yaml.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description="One-click GOAT-TS demo (cognition + optional reasoning).")
    parser.add_argument("--preset", type=str, default="quick-demo", help="Preset name from configs/presets.yaml")
    parser.add_argument("--dry-run", action="store_true", default=None, help="Force dry-run (in-memory).")
    parser.add_argument("--no-dry-run", action="store_true", help="Use live graph (Docker/Nebula required).")
    parser.add_argument("--reasoning-query", type=str, default="", help="After demo, run reasoning with this query.")
    parser.add_argument("--config", type=str, default="configs/graph.yaml", help="Graph config path.")
    args = parser.parse_args()

    dry_run = True
    if args.no_dry_run:
        dry_run = False
    elif args.dry_run:
        dry_run = True

    # Load preset
    preset_config = ROOT / "configs" / "presets.yaml"
    preset = args.preset
    if preset_config.exists():
        from src.utils import load_yaml_config
        data = load_yaml_config(preset_config)
        presets = data.get("presets") or {}
        if preset in presets:
            p = presets[preset]
            dry_run = dry_run if args.dry_run is not None else bool(p.get("dry_run", True))
            ticks = int(p.get("ticks", 5))
            seed_labels = p.get("seed_labels") or ["concept"]
            goal_labels = p.get("goal_labels") or []
            enable_forces = bool(p.get("enable_forces", False))
            enable_curiosity = bool(p.get("enable_curiosity", False))
            enable_goal_generator = bool(p.get("enable_goal_generator", False))
        else:
            ticks, seed_labels, goal_labels = 5, ["concept"], []
            enable_forces = enable_curiosity = enable_goal_generator = False
    else:
        ticks, seed_labels, goal_labels = 5, ["concept"], []
        enable_forces = enable_curiosity = enable_goal_generator = False

    config_path = str(ROOT / args.config)
    from src.agi_loop.demo_loop import run_demo
    from src.graph.client import NebulaGraphClient

    client = NebulaGraphClient(config_path=config_path, dry_run_override=dry_run)
    try:
        nodes, edges, summary = run_demo(
            client,
            seed_ids=[],
            seed_labels=seed_labels,
            goal_labels=goal_labels,
            ticks=ticks,
            enable_forces=enable_forces,
            enable_curiosity=enable_curiosity,
            enable_goal_generator=enable_goal_generator,
            config_path=config_path,
        )
    finally:
        client.close()

    print(f"Demo done: ticks={summary['ticks']}, nodes={len(nodes)}, edges={len(edges)}")

    if args.reasoning_query:
        from src.reasoning.loop import run_reasoning_loop
        response = run_reasoning_loop(args.reasoning_query.strip(), ROOT, live=not dry_run)
        print(f"Reasoning: tension={response.tension.score:.4f}, hypotheses={len(response.hypotheses)}")
        for h in response.hypotheses[:3]:
            print(f"  - {h.prompt[:70]}...")

    return 0


if __name__ == "__main__":
    sys.exit(main())
