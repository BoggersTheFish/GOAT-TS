"""
Stage 5: FastAPI server for run_demo and reasoning.
Run from repo root: uvicorn scripts.serve_api:app --reload --host 0.0.0.0 --port 8000
Requires: pip install uvicorn
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from fastapi import FastAPI, HTTPException
    from pydantic import BaseModel, Field
except ImportError:
    print("FastAPI and pydantic required. Install with: pip install fastapi uvicorn", file=sys.stderr)
    sys.exit(1)

app = FastAPI(title="GOAT-TS API", description="Cognition demo and reasoning endpoints", version="0.1.0")


class RunDemoRequest(BaseModel):
    ticks: int = Field(5, ge=1, le=100)
    dry_run: bool = True
    seed_labels: str = "concept"
    enable_forces: bool = False


class RunDemoResponse(BaseModel):
    ticks: int
    seed_count: int
    final_states: dict
    node_count: int
    edge_count: int


@app.post("/run_demo", response_model=RunDemoResponse)
def run_demo_endpoint(body: RunDemoRequest) -> RunDemoResponse:
    """Run the cognition demo loop (seeds → spread → memory_tick → optional forces)."""
    from src.agi_loop.demo_loop import run_demo
    from src.graph.client import NebulaGraphClient

    config_path = str(ROOT / "configs" / "graph.yaml")
    client = NebulaGraphClient(config_path=config_path, dry_run_override=body.dry_run)
    try:
        seed_labels = [s.strip() for s in body.seed_labels.split(",") if s.strip()] or ["concept"]
        nodes, edges, summary = run_demo(
            client,
            seed_ids=[],
            seed_labels=seed_labels,
            ticks=body.ticks,
            enable_forces=body.enable_forces,
            config_path=config_path,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        client.close()

    return RunDemoResponse(
        ticks=summary["ticks"],
        seed_count=summary["seed_count"],
        final_states=summary.get("final_states", {}),
        node_count=len(nodes),
        edge_count=len(edges),
    )


class ReasoningRequest(BaseModel):
    query: str = Field(..., min_length=1)
    live: bool = False


@app.post("/reasoning")
def reasoning_endpoint(body: ReasoningRequest) -> dict:
    """Run reasoning loop: query → activated nodes, tension, hypotheses."""
    from src.reasoning.loop import run_reasoning_loop

    try:
        response = run_reasoning_loop(body.query, ROOT, live=body.live)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {
        "query": response.query,
        "activated_count": len(response.activated_nodes),
        "tension_score": response.tension.score,
        "hypotheses_count": len(response.hypotheses),
        "hypotheses": [{"prompt": h.prompt, "rationale": h.rationale} for h in response.hypotheses[:5]],
    }


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
