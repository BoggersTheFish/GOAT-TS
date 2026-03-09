"""
Stage 5: API endpoint tests (FastAPI run_demo and reasoning).
Run: python -m pytest tests/test_serve_api.py -v
"""
from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def app():
    """Load FastAPI app for testing."""
    sys_path = list(__import__("sys").path)
    if str(ROOT) not in sys_path:
        __import__("sys").path.insert(0, str(ROOT))
    from scripts.serve_api import app as fastapi_app
    return fastapi_app


def test_health(app) -> None:
    """GET /health returns status ok."""
    from fastapi.testclient import TestClient
    client = TestClient(app)
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_run_demo_endpoint(app) -> None:
    """POST /run_demo with dry_run returns summary."""
    from fastapi.testclient import TestClient
    client = TestClient(app)
    r = client.post("/run_demo", json={"ticks": 2, "dry_run": True, "seed_labels": "concept"})
    assert r.status_code == 200
    data = r.json()
    assert data["ticks"] == 2
    assert "seed_count" in data
    assert "final_states" in data
    assert data["node_count"] >= 1
    assert data["edge_count"] >= 0


def test_reasoning_endpoint(app) -> None:
    """POST /reasoning returns query, tension, hypotheses."""
    from fastapi.testclient import TestClient
    client = TestClient(app)
    r = client.post("/reasoning", json={"query": "Wikipedia and knowledge", "live": False})
    assert r.status_code == 200
    data = r.json()
    assert data["query"] == "Wikipedia and knowledge"
    assert "tension_score" in data
    assert "hypotheses_count" in data
    assert isinstance(data["hypotheses"], list)
