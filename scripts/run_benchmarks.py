from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.reasoning.loop import ReasoningResponse, run_reasoning_loop  # noqa: E402
from src.ingestion.llm_extract import TripleExtractor  # noqa: E402
from src.utils import load_yaml_config  # noqa: E402


@dataclass(slots=True)
class CaseResult:
    id: str
    query: str
    expected_substring: str
    goat_hit: bool
    goat_tension_score: float
    goat_graph_nodes: int
    goat_graph_edges: int
    goat_latency_s: float
    llm_hit: bool
    llm_latency_s: float
    llm_enabled: bool


def _load_cases(path: Path, max_cases: int | None = None) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(data, list), "benchmarks.json must contain a JSON array"
    if max_cases is not None:
        data = data[:max_cases]
    return data


def _substring_hit(texts: list[str], needle: str) -> bool:
    if not needle:
        return False
    needle_lower = needle.lower()
    for t in texts:
        if needle_lower in (t or "").lower():
            return True
    return False


def _run_goat(query: str, expected: str) -> tuple[ReasoningResponse, bool, float]:
    t0 = time.perf_counter()
    response = run_reasoning_loop(query, ROOT, live=False)
    elapsed = time.perf_counter() - t0
    hypothesis_texts = [h.prompt for h in response.hypotheses]
    goat_texts = hypothesis_texts + response.activated_nodes
    hit = _substring_hit(goat_texts, expected)
    return response, hit, elapsed


def _run_llm_baseline(query: str, expected: str) -> tuple[bool, float, bool]:
    """
    Best-effort local LLM-style baseline.

    Uses TripleExtractor when enable_model_inference is true; otherwise falls
    back to regex extraction. This is intentionally simple: it treats the
    serialized triples as a "response" and checks for the expected substring.
    """
    cfg = load_yaml_config(ROOT / "configs" / "llm.yaml")["llm"]
    llm_enabled = bool(cfg.get("enable_model_inference", False))
    extractor = TripleExtractor(ROOT / "configs" / "llm.yaml")
    t0 = time.perf_counter()
    result = extractor.extract(query, require_llm=False)
    elapsed = time.perf_counter() - t0
    triples_text = [
        f"{t.subject} {t.relation} {t.object}" for t in result.triples
    ]
    hit = _substring_hit(triples_text, expected)
    return hit, elapsed, llm_enabled


def run_all_benchmarks(
    cases_path: Path,
    max_cases: int | None = None,
) -> dict[str, Any]:
    cases = _load_cases(cases_path, max_cases=max_cases)
    results: list[CaseResult] = []
    for raw in cases:
        case_id = str(raw.get("id"))
        query = str(raw.get("query"))
        expected = str(raw.get("expected_substring", "") or "")

        goat_response, goat_hit, goat_latency = _run_goat(query, expected)
        llm_hit, llm_latency, llm_enabled = _run_llm_baseline(query, expected)

        results.append(
            CaseResult(
                id=case_id,
                query=query,
                expected_substring=expected,
                goat_hit=goat_hit,
                goat_tension_score=goat_response.tension.score,
                goat_graph_nodes=goat_response.graph_context.get("nodes", 0),
                goat_graph_edges=goat_response.graph_context.get("edges", 0),
                goat_latency_s=goat_latency,
                llm_hit=llm_hit,
                llm_latency_s=llm_latency,
                llm_enabled=llm_enabled,
            )
        )

    total = len(results)
    goat_hits = sum(1 for r in results if r.goat_hit)
    llm_hits = sum(1 for r in results if r.llm_hit)

    summary = {
        "cases": [asdict(r) for r in results],
        "totals": {
            "count": total,
            "goat_hit_rate": float(goat_hits) / float(total or 1),
            "llm_hit_rate": float(llm_hits) / float(total or 1),
        },
    }
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run GOAT-TS reasoning benchmarks against simple LLM baseline."
    )
    parser.add_argument(
        "--cases-path",
        type=Path,
        default=ROOT / "examples" / "benchmarks.json",
        help="Path to benchmarks.json definition file.",
    )
    parser.add_argument(
        "--max-cases",
        type=int,
        default=None,
        help="Maximum number of cases to run (default: all).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional path to write JSON summary.",
    )
    args = parser.parse_args()

    summary = run_all_benchmarks(args.cases_path, max_cases=args.max_cases)
    text = json.dumps(summary, indent=2, default=str)
    print(text)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

