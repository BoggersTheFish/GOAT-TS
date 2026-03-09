from __future__ import annotations

import numpy as np

from src.graph.graph_engine import CognitiveGraph
from src.graph.models import Node


def test_graph_engine_adds_sparse_semantic_edges() -> None:
    graph = CognitiveGraph(max_edges_per_node=2, similarity_threshold=0.3)
    graph.add_node(Node(node_id="n1", label="gravity", embedding=[1.0, 0.0, 0.0]))
    graph.add_node(Node(node_id="n2", label="mass", embedding=[0.9, 0.1, 0.0]))
    graph.add_node(Node(node_id="n3", label="biology", embedding=[0.0, 1.0, 0.0]))

    assert graph.to_networkx().number_of_edges() >= 1
    nearest = graph.query_nearest(np.array([1.0, 0.0, 0.0], dtype=np.float32), k=2)
    assert nearest[0][1] >= nearest[1][1]

