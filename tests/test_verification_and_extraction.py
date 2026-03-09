"""
Tests for verification scripts and extraction pipeline: dry-run, sample text, round-trip.
No live NebulaGraph required.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_apply_schema_dry_run_exits_zero() -> None:
    """apply_schema.py --dry-run must exit 0 and print that it would apply schema."""
    r = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "apply_schema.py"), "--dry-run"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=30,
        env={**__import__("os").environ, "PYTHONPATH": str(ROOT)},
    )
    out = (r.stdout or "") + (r.stderr or "")
    assert r.returncode == 0, f"stdout: {r.stdout!r} stderr: {r.stderr!r}"
    assert "dry-run" in out.lower() or "Dry-run" in out, f"Expected dry-run message in: {out[:500]!r}"


def test_extraction_on_sample_text_produces_nodes_and_waves() -> None:
    """extract_from_texts on a few sentences (regex fallback) produces nodes, edges, waves."""
    from src.ingestion.extraction_pipeline import extract_from_texts

    texts = [
        "Wikipedia is a free encyclopedia. NebulaGraph supports graph queries.",
        "Python has many libraries. Docker supports containers.",
    ]
    nodes, edges, waves, in_wave_edges = extract_from_texts(
        texts, ROOT, use_clusters=True, max_nodes_per_label=10
    )
    # Regex extracts at least "X is/has/supports Y" from each sentence -> triples -> waves
    assert len(waves) >= 1
    assert len(nodes) >= 1
    # Either cluster nodes (topic:) or concept nodes
    assert all(hasattr(n, "label") for n in nodes)


def test_dump_graph_stats_dry_run_does_not_crash() -> None:
    """dump_graph_stats without --live runs against in-memory store and prints stats."""
    r = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "dump_graph_stats.py")],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert r.returncode == 0
    assert "nodes" in r.stdout.lower() or "mode" in r.stdout.lower()


def test_roundtrip_wave_concepts_dry_run() -> None:
    """Insert one wave + two concept nodes + in_wave edges; query back concepts in that wave."""
    from src.graph.client import NebulaGraphClient
    from src.graph.cognition import EDGE_IN_WAVE, WAVE_SOURCE_INGESTION
    from src.graph.models import Edge, MemoryState, Node, Wave

    client = NebulaGraphClient(ROOT / "configs" / "graph.yaml")
    wave_id = "test_wave_roundtrip"
    client.insert_waves([
        Wave(wave_id=wave_id, label="Test wave", source=WAVE_SOURCE_INGESTION, source_chunk_id="test"),
    ])
    client.insert_nodes([
        Node(node_id="c1", label="ConceptOne", state=MemoryState.ACTIVE),
        Node(node_id="c2", label="ConceptTwo", state=MemoryState.DORMANT),
    ])
    client.insert_edges([
        Edge(src_id="c1", dst_id=wave_id, relation=EDGE_IN_WAVE, weight=0.5),
        Edge(src_id="c2", dst_id=wave_id, relation=EDGE_IN_WAVE, weight=0.5),
    ])
    edges = client.list_in_wave_edges(wave_id=wave_id)
    concept_ids = {e.src_id for e in edges}
    nodes = client.get_nodes_by_ids(list(concept_ids))
    labels = {n.label for n in nodes if n}
    client.close()
    assert "ConceptOne" in labels
    assert "ConceptTwo" in labels
    assert len(edges) == 2
