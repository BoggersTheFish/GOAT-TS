"""Stage 10: Advanced evolution — meta-reasoning, self-assessment."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_repo_curiosity_scan() -> None:
    """repo_curiosity_scan returns a list of strings."""
    from src.reasoning.meta_reasoning import repo_curiosity_scan
    out = repo_curiosity_scan(ROOT)
    assert isinstance(out, list)
    assert all(isinstance(x, str) for x in out)


def test_roadmap_to_hypotheses() -> None:
    """roadmap_to_hypotheses returns list of dicts with prompt/rationale."""
    from src.reasoning.meta_reasoning import roadmap_to_hypotheses
    text = "Stage 6: Usability\nScope: Simplify setup."
    hyps = roadmap_to_hypotheses(text, limit=3)
    assert isinstance(hyps, list)
    for h in hyps:
        assert "prompt" in h
        assert "rationale" in h


def test_run_meta_reasoning() -> None:
    """run_meta_reasoning returns scan_summary and hypotheses."""
    from src.reasoning.meta_reasoning import run_meta_reasoning
    out = run_meta_reasoning(ROOT)
    assert "scan_summary" in out
    assert "hypotheses" in out


def test_self_assessment_demo_exits_zero() -> None:
    """self_assessment_demo runs and writes report, exits 0."""
    r = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "self_assessment_demo.py")],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=90,
        env={**__import__("os").environ, "PYTHONPATH": str(ROOT)},
    )
    assert r.returncode == 0
    report = ROOT / "examples" / "self_assessment_report.md"
    assert report.exists()
