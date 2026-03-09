"""
Stage 1: Core loop — seeds → spread → memory_tick → forces; CLI, logs, Graphviz.
Run: python -m pytest tests/milestone_roadmap_stage1.py -v
"""
from __future__ import annotations

from pathlib import Path

import pytest


def test_core_loop_run_demo_dry_run() -> None:
    """Run demo_loop dry-run: seeds → spread → memory_tick (no forces)."""
    from src.agi_loop.demo_loop import run_demo
    from src.graph.client import NebulaGraphClient

    root = Path(__file__).resolve().parents[1]
    config_path = str(root / "configs" / "graph.yaml")
    client = NebulaGraphClient(config_path=config_path, dry_run_override=True)
    try:
        nodes, edges, summary = run_demo(
            client,
            seed_ids=[],
            seed_labels=["concept"],
            ticks=3,
            decay_rate=0.95,
            enable_forces=False,
            verbose=False,
            config_path=config_path,
        )
    finally:
        client.close()

    assert len(nodes) >= 1
    assert "ticks" in summary
    assert summary["ticks"] == 3
    assert "final_states" in summary
    assert "active" in summary["final_states"]


def test_core_loop_export_dot() -> None:
    """Core loop with --export-dot produces a .dot file (Graphviz)."""
    import tempfile
    from src.agi_loop.demo_loop import run_demo
    from src.graph.client import NebulaGraphClient

    root = Path(__file__).resolve().parents[1]
    config_path = str(root / "configs" / "graph.yaml")
    client = NebulaGraphClient(config_path=config_path, dry_run_override=True)
    with tempfile.TemporaryDirectory() as tmp:
        dot_path = Path(tmp) / "out.dot"
        try:
            nodes, edges, summary = run_demo(
                client,
                seed_ids=[],
                seed_labels=["concept"],
                ticks=2,
                export_dot_path=str(dot_path),
                verbose=False,
                config_path=config_path,
            )
        finally:
            client.close()
        assert dot_path.exists()
        content = dot_path.read_text(encoding="utf-8")
        assert "digraph" in content or "graph" in content
