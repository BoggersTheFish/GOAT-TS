"""Stage 7: Real-world integrations — connectors, apps, API output_format."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_connectors_fetch_urls_empty() -> None:
    """fetch_urls with empty list returns [] and does not raise."""
    from src.ingestion.connectors import fetch_urls
    assert fetch_urls([]) == []


def test_connectors_rss_feed_to_chunks_empty_url() -> None:
    """rss_feed_to_chunks with empty URL returns []."""
    from src.ingestion.connectors import rss_feed_to_chunks
    assert rss_feed_to_chunks("") == []


def test_app_knowledge_explorer_stdout() -> None:
    """Knowledge explorer runs and outputs valid JSON to stdout."""
    r = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "app_knowledge_explorer.py"), "test query"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=30,
        env={**os.environ, "PYTHONPATH": str(ROOT)},
    )
    assert r.returncode == 0
    data = json.loads(r.stdout)
    assert "query" in data
    assert "nodes" in data
    assert "edges" in data


def test_app_qa_bot_single_query() -> None:
    """Q&A bot with --query runs and exits 0."""
    r = subprocess.run(
        [
            sys.executable, str(ROOT / "scripts" / "app_qa_bot.py"),
            "--query", "What is a knowledge graph?",
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=30,
        env={**os.environ, "PYTHONPATH": str(ROOT)},
    )
    assert r.returncode == 0
