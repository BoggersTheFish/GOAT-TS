"""Stage 6: Usability — presets, one-click demo, fallback paths."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_one_click_demo_dry_run() -> None:
    """One-click demo runs with default preset (dry-run) and exits 0."""
    r = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "one_click_demo.py"), "--preset", "quick-demo"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=60,
        env={**__import__("os").environ, "PYTHONPATH": str(ROOT)},
    )
    assert r.returncode == 0, (r.stdout, r.stderr)


def test_demo_loop_preset_quick_demo() -> None:
    """Demo loop --preset quick-demo runs without error."""
    r = subprocess.run(
        [
            sys.executable, "-m", "src.agi_loop.demo_loop",
            "--preset", "quick-demo", "--dry-run",
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=45,
        env={**__import__("os").environ, "PYTHONPATH": str(ROOT)},
    )
    assert r.returncode == 0, (r.stdout, r.stderr)


def test_presets_config_exists() -> None:
    """Presets config is loadable and has expected keys."""
    from src.utils import load_yaml_config
    path = ROOT / "configs" / "presets.yaml"
    assert path.exists()
    data = load_yaml_config(path)
    presets = data.get("presets") or {}
    assert "quick-demo" in presets
    assert "lightweight" in presets
