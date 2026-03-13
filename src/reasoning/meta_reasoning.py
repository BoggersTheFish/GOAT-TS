"""
Stage 10: Meta-reasoning — curiosity over repo/code (e.g. ROADMAP, file list) to suggest hypotheses.
Experimental: treat roadmap text as "query" and produce structured next-step or tension-style items.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def repo_curiosity_scan(repo_root: Path, *, max_files: int = 20) -> list[str]:
    """
    List notable files (ROADMAP, README, CHANGELOG, .py under src/) for meta-reasoning.
    Returns list of short descriptive strings (path + one line) for context.
    """
    out: list[str] = []
    for name in ["ROADMAP.md", "README.md", "CHANGELOG.md", "CONTRIBUTING.md"]:
        p = repo_root / name
        if p.exists():
            try:
                line = next(iter(p.read_text(encoding="utf-8").splitlines()), "").strip()[:80]
                out.append(f"{name}: {line}")
            except Exception:
                out.append(name)
    seen = 0
    for py in sorted((repo_root / "src").rglob("*.py"))[:max_files]:
        if seen >= max_files:
            break
        try:
            mod = py.relative_to(repo_root)
            out.append(f"src/{mod}")
        except ValueError:
            pass
        seen += 1
    return out


def roadmap_to_hypotheses(roadmap_text: str, *, limit: int = 5) -> list[dict[str, Any]]:
    """
    Parse roadmap-like text and return a list of hypothesis-shaped items (prompt, rationale).
    Heuristic: look for "Stage", "Scope", "Run:", "Tests:" and turn them into open questions.
    """
    hypotheses: list[dict[str, Any]] = []
    lines = roadmap_text.splitlines()
    for i, line in enumerate(lines):
        if "Stage " in line and ":" in line:
            stage = line.split(":")[0].strip()
            rest = line.split(":", 1)[-1].strip()[:100]
            hypotheses.append({
                "prompt": f"What is the next step for {stage}?",
                "rationale": rest or "Roadmap stage.",
            })
        if "Scope:" in line and i + 1 < len(lines):
            scope = lines[i + 1].strip()[:120]
            hypotheses.append({
                "prompt": f"Scope: {scope} — is this implemented?",
                "rationale": "From roadmap scope.",
            })
        if len(hypotheses) >= limit:
            break
    return hypotheses[:limit]


def run_meta_reasoning(repo_root: Path) -> dict[str, Any]:
    """
    Run a lightweight meta-reasoning pass: scan repo, read ROADMAP, return hypotheses and scan summary.
    """
    scan = repo_curiosity_scan(repo_root)
    roadmap_path = repo_root / "ROADMAP.md"
    roadmap_text = roadmap_path.read_text(encoding="utf-8") if roadmap_path.exists() else ""
    hypotheses = roadmap_to_hypotheses(roadmap_text)
    return {
        "scan_summary": scan[:15],
        "hypotheses": hypotheses,
        "roadmap_preview": roadmap_text[:500] if roadmap_text else "",
    }
