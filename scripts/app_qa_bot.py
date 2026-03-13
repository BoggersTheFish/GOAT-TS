"""
Stage 7: Simple Q&A bot — loop: read query, call reasoning API (or in-process), print hypotheses.
Run from repo root. Uses dry-run by default (no Docker). For live: set LIVE=1 or --live.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description="GOAT-TS Q&A bot: query → reasoning → hypotheses.")
    parser.add_argument("--query", type=str, default="", help="Single query (else interactive).")
    parser.add_argument("--live", action="store_true", help="Use live graph.")
    parser.add_argument("--api", type=str, default="", help="If set, call API at this URL (e.g. http://localhost:8000).")
    args = parser.parse_args()

    live = args.live or (sys.environ.get("LIVE") == "1")

    def run_reasoning(q: str) -> dict:
        if args.api:
            try:
                import urllib.request
                import json
                data = json.dumps({"query": q, "live": live, "output_format": "app"}).encode()
                req = urllib.request.Request(
                    f"{args.api.rstrip('/')}/reasoning",
                    data=data,
                    method="POST",
                    headers={"Content-Type": "application/json"},
                )
                with urllib.request.urlopen(req, timeout=30) as r:
                    return json.loads(r.read().decode())
            except Exception as e:
                return {"error": str(e), "hypotheses": []}
        from src.reasoning.loop import run_reasoning_loop
        r = run_reasoning_loop(q, ROOT, live=live)
        return {
            "query": r.query,
            "tension_score": r.tension.score,
            "hypotheses": [{"prompt": h.prompt, "rationale": h.rationale} for h in r.hypotheses[:10]],
        }

    if args.query:
        out = run_reasoning(args.query.strip())
        if out.get("error"):
            print("Error:", out["error"], file=sys.stderr)
            return 1
        print("Tension:", out.get("tension_score", 0))
        for h in out.get("hypotheses") or []:
            print(" -", h.get("prompt", "")[:80])
        return 0

    # Interactive
    print("GOAT-TS Q&A bot (dry-run by default). Type a query and press Enter; empty to exit.")
    while True:
        try:
            q = input("Query> ").strip()
        except EOFError:
            break
        if not q:
            break
        out = run_reasoning(q)
        if out.get("error"):
            print("Error:", out["error"])
            continue
        for h in out.get("hypotheses") or []:
            print(" -", h.get("prompt", "")[:80])
    return 0


if __name__ == "__main__":
    sys.exit(main())
