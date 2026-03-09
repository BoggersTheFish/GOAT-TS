from __future__ import annotations

import logging
import numpy as np

logger = logging.getLogger(__name__)


def approximate_neighbor_pairs(
    positions: np.ndarray,
    k: int = 50,
    *,
    use_faiss: bool = True,
) -> list[tuple[int, int]]:
    """
    Return list of (i, j) index pairs that are approximate k-NN by position (L2).
    Each pair appears once with i < j. Used to limit force calculations to nearby nodes (FAISS ANN).
    """
    n = positions.shape[0]
    if n <= 1:
        return []
    positions = np.asarray(positions, dtype=np.float32)
    if positions.ndim == 1:
        positions = positions.reshape(-1, 1)
    dim = positions.shape[1]
    k = min(k, n - 1)
    if k <= 0:
        return []

    if use_faiss:
        try:
            import faiss
        except ImportError:
            use_faiss = False
    if use_faiss:
        index = faiss.IndexFlatL2(dim)
        index.add(positions)
        distances, indices = index.search(positions, k + 1)  # +1 to drop self
        pairs: set[tuple[int, int]] = set()
        for i in range(n):
            for j_idx in indices[i]:
                j = int(j_idx)
                if j < 0 or i == j:
                    continue
                pairs.add((min(i, j), max(i, j)))
        return sorted(pairs)
    # Fallback: all pairs (no FAISS) - caller can avoid using this for large n
    return [(i, j) for i in range(n) for j in range(i + 1, n)]


def _safe_direction(source: np.ndarray, target: np.ndarray) -> tuple[np.ndarray, float]:
    delta = np.asarray(target, dtype=np.float32) - np.asarray(source, dtype=np.float32)
    distance = float(np.linalg.norm(delta))
    if distance == 0.0:
        return np.zeros(3, dtype=np.float32), 0.0
    return delta / distance, distance


def attraction_force(
    source_position: np.ndarray,
    target_position: np.ndarray,
    similarity: float,
    attraction_constant: float,
    epsilon: float,
) -> np.ndarray:
    direction, distance = _safe_direction(source_position, target_position)
    magnitude = attraction_constant * max(similarity, 0.0) / ((distance**2) + epsilon)
    return direction * magnitude


def repulsion_force(
    source_position: np.ndarray,
    target_position: np.ndarray,
    repulsion_constant: float,
    epsilon: float,
) -> np.ndarray:
    direction, distance = _safe_direction(source_position, target_position)
    magnitude = repulsion_constant / ((distance**2) + epsilon)
    return -direction * magnitude


def spring_force(
    source_position: np.ndarray,
    target_position: np.ndarray,
    similarity: float,
    spring_constant: float,
    ideal_length_base: float,
) -> np.ndarray:
    direction, distance = _safe_direction(source_position, target_position)
    ideal_length = ideal_length_base * max(0.15, 1.0 - max(similarity, 0.0))
    magnitude = -spring_constant * (distance - ideal_length)
    return direction * magnitude

