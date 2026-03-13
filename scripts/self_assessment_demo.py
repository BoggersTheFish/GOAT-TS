"""
Stage 10: Self-assessment demo — run benchmarks and write a short Markdown report.
Useful for CI or local "how am I doing?" check. No Docker required (dry-run).
"""
from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    spec = importlib.util.spec_from_file_location(
        "run_benchmarks",
        ROOT / "scripts" / "run_benchmarks.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    summary = mod.run_all_benchmarks(ROOT / "examples" / "benchmarks.json", max_cases=5)
    totals = summary.get("totals") or {}
    count = totals.get("count", 0)
    goat_rate = totals.get("goat_hit_rate", 0.0)
    llm_rate = totals.get("llm_hit_rate", 0.0)

    report_lines = [
        "# GOAT-TS self-assessment report",
        f"Generated: {datetime.utcnow().isoformat()}Z",
        "",
        "## Benchmark summary",
        f"- Cases run: {count}",
        f"- GOAT hit rate: {goat_rate:.2%}",
        f"- LLM baseline hit rate: {llm_rate:.2%}",
        "",
        "## Raw JSON (excerpt)",
        "```json",
        json.dumps(totals, indent=2),
        "```",
        "",
        "---",
        "Run full benchmarks: `python scripts/run_benchmarks.py --output report.json`",
    ]
    report_path = ROOT / "examples" / "self_assessment_report.md"
    report_path.write_text("\n".join(report_lines), encoding="utf-8")
    print(f"Wrote {report_path}")
    print(f"GOAT hit rate: {goat_rate:.2%} ({count} cases)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
