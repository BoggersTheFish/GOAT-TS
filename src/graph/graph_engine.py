from __future__ import annotations

from dataclasses import replace

import networkx as nx
import numpy as np
from sentence_transformers import SentenceTransformer

from src.graph.constraints import cosine_similarity, knn_edges
from src.graph.models import Edge, Node


class CognitiveGraph:
    """In-memory semantic graph with sparse k-NN edges."""

    def __init__(
        self,
        embedding_model_name: str = "all-MiniLM-L6-v2",
        max_edges_per_node: int = 8,
        similarity_threshold: float = 0.3,
    ) -> None:
        self._graph = nx.Graph()
        self._model_name = embedding_model_name
        self._max_edges_per_node = max_edges_per_node
        self._similarity_threshold = similarity_threshold
        self._embedder = None

    def _get_embedder(self):
        if self._embedder is None:
            self._embedder = SentenceTransformer(self._model_name)
        return self._embedder

    def embed_text(self, text: str) -> np.ndarray:
        try:
            embedder = self._get_embedder()
            vec = embedder.encode(text, normalize_embeddings=True)
            return np.asarray(vec, dtype=np.float32)
        except Exception:
            seed = abs(hash(text.lower().strip())) % (2**32)
            rng = np.random.default_rng(seed)
            vec = rng.standard_normal(384).astype(np.float32)
            norm = np.linalg.norm(vec)
            return vec if norm == 0.0 else vec / norm

    def add_node(self, node: Node) -> str:
        embedding = node.embedding_array()
        if embedding is None:
            embedding = self.embed_text(node.label)
            node = replace(node, embedding=embedding.tolist())
        self._graph.add_node(
            node.node_id,
            node=node,
            embedding=embedding,
            position=node.position_array(),
            velocity=node.velocity_array(),
        )
        self._recompute_sparse_edges()
        return node.node_id

    def add_edge(self, edge: Edge) -> None:
        if self._graph.has_node(edge.src_id) and self._graph.has_node(edge.dst_id):
            self._graph.add_edge(edge.src_id, edge.dst_id, weight=edge.weight, relation=edge.relation, metadata=edge.metadata)

    def get_node(self, node_id: str) -> Node | None:
        if not self._graph.has_node(node_id):
            return None
        return self._graph.nodes[node_id]["node"]

    def query_nearest(self, embedding: np.ndarray, k: int = 5) -> list[tuple[str, float]]:
        if self._graph.number_of_nodes() == 0:
            return []
        scores = []
        for node_id, attrs in self._graph.nodes(data=True):
            sim = cosine_similarity(embedding, attrs["embedding"])
            scores.append((node_id, sim))
        scores.sort(key=lambda item: item[1], reverse=True)
        return scores[:k]

    def find_nearest_text(self, query: str, k: int = 5) -> list[tuple[Node, float]]:
        query_embedding = self.embed_text(query)
        return [
            (self._graph.nodes[node_id]["node"], score)
            for node_id, score in self.query_nearest(query_embedding, k=k)
        ]

    def to_networkx(self) -> nx.Graph:
        return self._graph

    def _recompute_sparse_edges(self) -> None:
        for u, v in list(self._graph.edges()):
            self._graph.remove_edge(u, v)
        node_ids = list(self._graph.nodes())
        if not node_ids:
            return
        embeddings = np.array([self._graph.nodes[nid]["embedding"] for nid in node_ids], dtype=np.float32)
        seen: set[tuple[str, str]] = set()
        for src_id, dst_id, weight in knn_edges(
            node_ids,
            embeddings,
            self._max_edges_per_node,
            self._similarity_threshold,
        ):
            pair = tuple(sorted((src_id, dst_id)))
            if pair in seen:
                continue
            seen.add(pair)
            self._graph.add_edge(src_id, dst_id, weight=weight, relation="semantic_similarity", metadata={})

