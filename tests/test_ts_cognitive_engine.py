"""Smoke tests for the TS Cognitive Graph Engine subproject."""

from __future__ import annotations

import numpy as np

from ts_cognitive_engine.core import KnowledgeNode, TSCognitiveGraph
from ts_cognitive_engine.physics import PhysicsEngine


def test_graph_auto_connects_semantic_neighbors():
    graph = TSCognitiveGraph(similarity_threshold=0.1)
    graph.add_node(KnowledgeNode(text="gravity", embedding=np.array([1.0, 0.0, 0.0])))
    graph.add_node(KnowledgeNode(text="mass", embedding=np.array([0.9, 0.1, 0.0])))
    graph.add_node(KnowledgeNode(text="biology", embedding=np.array([0.0, 1.0, 0.0])))

    assert graph._graph.number_of_edges() >= 1
    nearest = graph.query_nearest(np.array([1.0, 0.0, 0.0]), k=2)
    assert nearest[0][1] >= nearest[1][1]


def test_layout_step_updates_positions():
    graph = TSCognitiveGraph(similarity_threshold=0.0)
    graph.add_node(KnowledgeNode(text="gravity", embedding=np.array([1.0, 0.0, 0.0])))
    graph.add_node(KnowledgeNode(text="mass", embedding=np.array([0.8, 0.2, 0.0]), position=np.array([0.0, 1.0, 0.0])))
    initial = np.asarray(graph.get_node(next(iter(graph._graph.nodes)))["position"]).copy()

    graph.set_physics_engine(PhysicsEngine(graph))
    graph.layout_step(dt=0.05, iterations=3)

    updated = np.asarray(graph.get_node(next(iter(graph._graph.nodes)))["position"])
    assert not np.allclose(initial, updated)

