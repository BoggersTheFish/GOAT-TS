"""
FAISS-backed vector index for node embeddings. Embeddings remain in node metadata;
this module provides approximate similarity search without Nebula vector type.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)


def _normalize_rows(x: np.ndarray) -> np.ndarray:
    """L2-normalize rows so that IndexFlatIP yields cosine similarity."""
    norms = np.linalg.norm(x, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1.0, norms)
    return np.asarray(x / norms, dtype=np.float32)


class EmbeddingVectorIndex:
    """
    External vector index over (node_id, embedding). Uses FAISS IndexFlatIP
    on L2-normalized vectors for cosine similarity. Embeddings are stored
    in node metadata in Nebula; this index is built in-memory (and optionally
    persisted to disk) for fast similarity search and global concept merging.
    """

    def __init__(self, dimension: int, index_path: Optional[Path] = None) -> None:
        self.dimension = dimension
        self.index_path = index_path
        self._index: Optional[object] = None
        self._id_list: list[str] = []
        self._vectors: Optional[np.ndarray] = None  # normalized, for find_similar_pairs
        self._built = False

    def _get_faiss_index(self):
        try:
            import faiss
        except ImportError as e:
            raise RuntimeError(
                "FAISS is required for vector index. Install with: pip install faiss-cpu"
            ) from e
        if self._index is None:
            self._index = faiss.IndexFlatIP(self.dimension)
        return self._index

    def add(self, node_ids: list[str], embeddings: np.ndarray) -> None:
        """Add or update vectors. embeddings shape (n, dimension)."""
        if len(node_ids) != embeddings.shape[0]:
            raise ValueError("node_ids length must match embeddings.shape[0]")
        embeddings = np.asarray(embeddings, dtype=np.float32)
        if embeddings.shape[1] != self.dimension:
            raise ValueError(f"embeddings.shape[1] must be {self.dimension}")
        vecs = _normalize_rows(embeddings)
        index = self._get_faiss_index()
        index.add(vecs)
        self._id_list.extend(node_ids)
        self._vectors = np.vstack([self._vectors, vecs]) if self._vectors is not None else vecs
        self._built = True

    def search_by_threshold(
        self,
        query_embedding: np.ndarray,
        threshold: float,
        k_max: int = 100,
    ) -> list[tuple[str, float]]:
        """
        Return (node_id, similarity) for all vectors with cosine similarity >= threshold.
        query_embedding: shape (dimension,) or (1, dimension).
        """
        if not self._id_list:
            return []
        q = np.asarray(query_embedding, dtype=np.float32).reshape(1, -1)
        if q.shape[1] != self.dimension:
            raise ValueError(f"query dimension must be {self.dimension}")
        q = _normalize_rows(q)
        index = self._get_faiss_index()
        k = min(k_max, index.ntotal)
        scores, indices = index.search(q, k)
        out: list[tuple[str, float]] = []
        for j, idx in enumerate(indices[0]):
            if idx < 0:
                break
            sim = float(scores[0][j])
            if sim >= threshold:
                out.append((self._id_list[idx], sim))
        return out

    def search_knn(self, query_embedding: np.ndarray, k: int = 10) -> list[tuple[str, float]]:
        """Return top-k (node_id, similarity) by cosine similarity."""
        if not self._id_list or k <= 0:
            return []
        q = np.asarray(query_embedding, dtype=np.float32).reshape(1, -1)
        q = _normalize_rows(q)
        index = self._get_faiss_index()
        k = min(k, index.ntotal)
        scores, indices = index.search(q, k)
        return [
            (self._id_list[int(idx)], float(scores[0][i]))
            for i, idx in enumerate(indices[0])
            if idx >= 0
        ]

    def find_similar_pairs(
        self,
        threshold: float,
        exclude_self: bool = True,
    ) -> list[tuple[str, str, float]]:
        """
        For each vector, find others with similarity >= threshold. Returns
        (id_a, id_b, similarity) for each pair (each pair once, id_a < id_b).
        """
        if not self._id_list or self._vectors is None:
            return []
        index = self._get_faiss_index()
        n = index.ntotal
        scores, indices = index.search(self._vectors, n)
        seen: set[tuple[str, str]] = set()
        pairs: list[tuple[str, str, float]] = []
        for i in range(n):
            id_i = self._id_list[i]
            for j_idx, sim in zip(indices[i], scores[i]):
                j = int(j_idx)
                if j < 0:
                    break
                if exclude_self and i == j:
                    continue
                if sim < threshold:
                    continue
                id_j = self._id_list[j]
                key = tuple(sorted((id_i, id_j)))
                if key in seen:
                    continue
                seen.add(key)
                pairs.append((id_i, id_j, float(sim)))
        return pairs

    def save(self, path: Optional[Path] = None) -> None:
        """Persist FAISS index, id list, and vectors to directory."""
        import pickle
        p = path or self.index_path
        if p is None:
            raise ValueError("No index_path provided")
        p = Path(p)
        p.mkdir(parents=True, exist_ok=True)
        index = self._get_faiss_index()
        faiss_path = p / "index.faiss"
        try:
            import faiss
            faiss.write_index(index, str(faiss_path))
        except Exception as e:
            logger.warning("Could not save FAISS index: %s", e)
            return
        data_path = p / "ids_vectors.pkl"
        with open(data_path, "wb") as f:
            pickle.dump((self._id_list, self._vectors), f)

    def load(self, path: Optional[Path] = None) -> None:
        """Load FAISS index, id list, and vectors from directory."""
        import pickle
        try:
            import faiss
        except ImportError:
            raise RuntimeError("FAISS required to load index. pip install faiss-cpu") from None
        p = path or self.index_path
        if p is None:
            raise ValueError("No index_path provided")
        p = Path(p)
        faiss_path = p / "index.faiss"
        data_path = p / "ids_vectors.pkl"
        if not faiss_path.exists() or not data_path.exists():
            raise FileNotFoundError(f"Index not found at {p}")
        self._index = faiss.read_index(str(faiss_path))
        with open(data_path, "rb") as f:
            data = pickle.load(f)
            if isinstance(data, tuple) and len(data) == 2:
                self._id_list, self._vectors = data
            else:
                self._id_list = data
                self._vectors = None
        self._built = True

    @property
    def num_vectors(self) -> int:
        return len(self._id_list)
