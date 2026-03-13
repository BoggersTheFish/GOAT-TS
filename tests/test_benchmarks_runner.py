from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_run_benchmarks_script_smoke(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    out_path = tmp_path / "benchmarks_out.json"
    cmd = [
        sys.executable,
        str(root / "scripts" / "run_benchmarks.py"),
        "--max-cases",
        "1",
        "--output",
        str(out_path),
    ]
    result = subprocess.run(
        cmd,
        cwd=str(root),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert result.returncode == 0, result.stderr
    assert out_path.exists()
    data = json.loads(out_path.read_text(encoding="utf-8"))
    assert "cases" in data and isinstance(data["cases"], list)
    assert "totals" in data

