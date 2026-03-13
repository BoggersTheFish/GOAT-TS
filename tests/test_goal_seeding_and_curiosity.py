from __future__ import annotations

from pathlib import Path

from src.agi_loop.demo_loop import run_demo
from src.graph.client import NebulaGraphClient
from src.reasoning.curiosity import curiosity_query


def test_goal_labels_are_accepted_in_run_demo() -> None:
    """
    Ensure run_demo accepts goal_labels and runs in dry-run mode without error.
    """
    client = NebulaGraphClient(config_path="configs/graph.yaml", dry_run_override=True)
    try:
        nodes, edges, summary = run_demo(
            client,
            seed_ids=[],
            seed_labels=["concept"],
            goal_labels=["gravity", "physics"],
            ticks=2,
        )
    finally:
        client.close()
    assert isinstance(nodes, list)
    assert isinstance(edges, list)
    assert summary["ticks"] == 2


def test_curiosity_query_never_raises_on_missing_backends() -> None:
    """
    Curiosity should return a dict even when graph/web/ingestion backends are not configured.
    """
    root = Path(__file__).resolve().parents[1]
    result = curiosity_query("test curiosity query", root, live=False)
    assert isinstance(result, dict)
    assert "triggered" in result

