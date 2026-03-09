"""
Stage 2: Online learning, reflection.
Run: python -m pytest tests/milestone_roadmap_stage2.py -v
"""
from __future__ import annotations

from pathlib import Path


def test_reflection_produces_meta_waves_or_hypotheses() -> None:
    """run_reflection returns ReflectionResult with meta_waves and hypothesis_nodes."""
    from src.graph.models import Edge, MemoryState, Node
    from src.reasoning.reflection import run_reflection
    from src.reasoning.tension import TensionResult

    nodes = [
        Node(node_id="a", label="A", mass=1.0, activation=0.5, state=MemoryState.ACTIVE, position=[0.0, 0.0, 0.0]),
        Node(node_id="b", label="B", mass=1.0, activation=0.3, state=MemoryState.DORMANT, position=[1.0, 0.0, 0.0]),
    ]
    edges = [Edge(src_id="a", dst_id="b", relation="relates", weight=0.5)]
    tension = TensionResult(score=1.0, high_tension_pairs=[("a", "b", 0.8)])
    result = run_reflection(nodes, edges, tension=tension, create_meta_wave=False, hypothesis_limit=2)
    assert result.tension.score == 1.0
    assert isinstance(result.meta_waves, list)
    assert isinstance(result.hypothesis_nodes, list)


def test_self_reflection_detects_gaps_and_generates_goals() -> None:
    """Long-term self-reflection: wave gaps -> goal nodes."""
    from src.graph.models import NodeType, Wave
    from src.reasoning.self_reflection import detect_wave_gaps, generate_goal_nodes_for_gaps, run_long_term_self_reflection

    # No created_at -> index-based gap only (source_chunk_id with numbers)
    waves = [
        Wave(wave_id="w0", label="L0", source="ingestion", source_chunk_id="chunk_0"),
        Wave(wave_id="w1", label="L1", source="ingestion", source_chunk_id="chunk_10"),
    ]
    gaps = detect_wave_gaps(waves, gap_index_count=5)
    # chunk_0 -> chunk_10 has 9 missing indices
    assert len(gaps) >= 1
    goals = generate_goal_nodes_for_gaps(gaps, max_goals=3)
    assert len(goals) >= 1
    assert all(g.node_type == NodeType.GOAL for g in goals)

    gaps2, goals2 = run_long_term_self_reflection(waves, gap_index_count=5, max_goal_nodes=2)
    assert len(goals2) >= 1


def test_query_handler_decompose_and_tfidf_stub() -> None:
    """Query handler: decompose_query and handle_query path (no live search)."""
    from src.graph.query_handler import decompose_query

    terms = decompose_query("What is the capital of France?", max_terms=5)
    assert isinstance(terms, list)
    assert "france" in [t.lower() for t in terms] or "capital" in [t.lower() for t in terms]
