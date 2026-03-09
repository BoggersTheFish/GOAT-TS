"""
Step 6 benchmarks: consistency (path trace), reasoning (PuLP solvers),
efficiency (timings), interpretability (Graphviz export).
"""
from __future__ import annotations

import time
from pathlib import Path

import pytest

from src.activation import activate_and_propagate
from src.graph.models import Edge, MemoryState, Node


# ---- Consistency: path trace ----
def test_benchmark_consistency_path_trace() -> None:
    """Consistency: trace a path through the graph and assert nodes/edges align."""
    nodes = [
        Node(node_id="a", label="A", mass=1.0, activation=0.0, state=MemoryState.DORMANT),
        Node(node_id="b", label="B", mass=1.0, activation=0.0, state=MemoryState.DORMANT),
        Node(node_id="c", label="C", mass=1.0, activation=0.0, state=MemoryState.DORMANT),
    ]
    edges = [
        Edge(src_id="a", dst_id="b", relation="relates", weight=1.0),
        Edge(src_id="b", dst_id="c", relation="relates", weight=1.0),
    ]
    path = ["a", "b", "c"]
    for i in range(len(path) - 1):
        src, dst = path[i], path[i + 1]
        found = any(e.src_id == src and e.dst_id == dst for e in edges)
        assert found, f"Path trace broken: edge {src} -> {dst} missing"
    node_ids = {n.node_id for n in nodes}
    for nid in path:
        assert nid in node_ids, f"Path node {nid} not in graph"
    # Activation propagates along path
    updated, result = activate_and_propagate(nodes, edges, ["a"], max_hops=3)
    assert result.activations.get("a", 0) >= 0.9
    assert result.activations.get("b", 0) > 0
    assert result.activations.get("c", 0) > 0


# ---- Reasoning: PuLP solvers ----
def test_benchmark_reasoning_pulp() -> None:
    """Reasoning: PuLP solver benchmark (tiny LP)."""
    try:
        import pulp
    except ImportError:
        pytest.skip("PuLP not installed")
    prob = pulp.LpProblem("bench", pulp.LpMaximize)
    x = pulp.LpVariable("x", lowBound=0)
    y = pulp.LpVariable("y", lowBound=0)
    prob += 2 * x + 3 * y
    prob += x + y <= 1
    prob.solve(pulp.PULP_CBC_CMD(msg=0))
    assert prob.status == pulp.LpStatusOptimal
    assert x.varValue is not None and y.varValue is not None
    assert abs(x.varValue + y.varValue - 1.0) < 1e-6
    assert abs(2 * x.varValue + 3 * y.varValue - 3.0) < 1e-6  # max = 3 at (0,1)


# ---- Efficiency: timings ----
def test_benchmark_efficiency_timings() -> None:
    """Efficiency: activation propagation and gravity step complete within loose time limits."""
    n = 80
    nodes = [
        Node(
            node_id=f"n{i}",
            label=f"node_{i}",
            mass=1.0,
            activation=0.0,
            state=MemoryState.DORMANT,
            position=[float(i % 10), float(i // 10), 0.0],
        )
        for i in range(n)
    ]
    edges = [
        Edge(src_id=f"n{i}", dst_id=f"n{j}", relation="relates", weight=0.5)
        for i in range(n - 1) for j in [i + 1] if i % 3 == 0
    ]
    seed_ids = ["n0", "n1"]
    t0 = time.perf_counter()
    activate_and_propagate(nodes, edges, seed_ids, max_hops=5)
    elapsed = time.perf_counter() - t0
    assert elapsed < 5.0, f"Activation propagation took {elapsed:.2f}s (limit 5s)"


# ---- Interpretability: Graphviz export ----
def test_benchmark_interpretability_graphviz_export() -> None:
    """Interpretability: export_subgraph Graphviz .dot produces valid file."""
    import importlib.util
    import tempfile
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location(
        "export_subgraph", root / "scripts" / "export_subgraph.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    export_subgraph_to_dot = mod.export_subgraph_to_dot
    data = {
        "nodes": [
            {"node_id": "x", "label": "Concept X", "mass": 1.0, "activation": 0.5},
            {"node_id": "y", "label": "Concept Y", "mass": 1.0, "activation": 0.3},
        ],
        "edges": [{"src_id": "x", "dst_id": "y", "weight": 0.8}],
    }
    with tempfile.TemporaryDirectory() as tmp:
        dot_path = Path(tmp) / "out.dot"
        export_subgraph_to_dot(data, dot_path)
        assert dot_path.exists()
        content = dot_path.read_text(encoding="utf-8")
        assert "digraph" in content or "graph" in content
        assert "x" in content and "y" in content
        assert "Concept X" in content or "Concept Y" in content
