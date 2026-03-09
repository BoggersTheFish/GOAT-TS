from __future__ import annotations

from pathlib import Path

from src.graph.models import Edge, Node
from src.reasoning import loop as reasoning_loop


def test_reasoning_uses_memory_before_search_term_expansion(monkeypatch) -> None:
    root = Path(__file__).resolve().parents[1]

    class FakeExtractor:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def extract(self, query: str):
            return type("ExtractionResult", (), {"triples": [], "raw_response": "fake"})()

        def suggest_search_terms(self, query: str, max_terms: int = 10):
            raise AssertionError("Search-term expansion should not run when local graph memory matched.")

    def fake_retrieve_graph_context(query: str, config_root: Path, live: bool, node_limit: int = 200, edge_limit: int = 1000, *, extra_keywords=None):
        return [Node(node_id="a", label="local concept", activation=0.5)], [Edge(src_id="a", dst_id="a", weight=1.0)]

    monkeypatch.setattr(reasoning_loop, "TripleExtractor", FakeExtractor)
    monkeypatch.setattr(reasoning_loop, "retrieve_graph_context", fake_retrieve_graph_context)

    response = reasoning_loop.run_reasoning_loop("local concept", root, live=False)
    assert response.graph_context["nodes"] == 1


def test_retrieve_graph_context_expands_linked_context_and_gravity_neighbors(monkeypatch) -> None:
    root = Path(__file__).resolve().parents[1]

    seed = Node(node_id="seed", label="gravity seed", activation=0.8)
    linked = Node(node_id="linked", label="mass neighbor", activation=0.6)
    gravity = Node(
        node_id="gravity",
        label="curvature context",
        activation=0.4,
        metadata={
            "gravity_links": {
                "seed": {"gravity_value": 0.9, "edge_weight": 0.5},
            }
        },
    )
    edges = [Edge(src_id="seed", dst_id="linked", weight=0.7)]

    class FakeClient:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def list_cluster_nodes(self, limit: int = 500):
            return []

        def snapshot(self, node_limit=200, edge_limit=1000, label_keywords=None, cluster_ids=None):
            return {
                "nodes": [
                    {"node_id": "seed", "label": "gravity seed", "mass": 1.0, "activation": 0.8, "state": "active", "cluster_id": "", "metadata": {}},
                    {"node_id": "gravity", "label": "curvature context", "mass": 1.0, "activation": 0.4, "state": "dormant", "cluster_id": "", "metadata": gravity.metadata},
                ],
                "edges": [],
            }

        def neighbors(self, node_id: str):
            return ["linked"] if node_id == "seed" else []

        def get_nodes_by_ids(self, node_ids):
            out = []
            if "linked" in node_ids:
                out.append(linked)
            return out

        def list_edges_between(self, node_ids, limit=1000):
            out = []
            node_set = set(node_ids)
            for edge in edges:
                if edge.src_id in node_set and edge.dst_id in node_set:
                    out.append(edge)
            return out

        def list_waves(self, limit: int = 100):
            return []

        def list_in_wave_edges(self, wave_id=None, limit: int = 500):
            return []

        def list_nodes(self, limit: int = 200):
            return [seed, linked, gravity]

        def close(self):
            return None

    monkeypatch.setattr(reasoning_loop, "NebulaGraphClient", FakeClient)

    nodes, found_edges = reasoning_loop.retrieve_graph_context("gravity", root, live=False)
    node_ids = {node.node_id for node in nodes}

    assert "seed" in node_ids
    assert "linked" in node_ids
    assert "gravity" in node_ids
    assert any(edge.src_id == "seed" and edge.dst_id == "linked" for edge in found_edges)

