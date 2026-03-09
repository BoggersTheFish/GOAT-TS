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


def layout_fruchterman_reingold(
    positions: np.ndarray,
    edge_index: np.ndarray,
    *,
    iterations: int = 50,
    k: float | None = None,
    scale: float = 1.0,
) -> np.ndarray:
    """
    Fruchterman-Reingold force-directed layout. positions (n, dim), edge_index (2, E) with node indices.
    Returns new positions (n, dim). Uses repulsion between all pairs and attraction along edges.
    """
    n, dim = positions.shape
    if n == 0:
        return positions
    pos = np.asarray(positions, dtype=np.float32).copy()
    if k is None:
        k = scale * (1.0 / n) ** 0.5 if n > 0 else 1.0
    for _ in range(iterations):
        disp = np.zeros_like(pos)
        # Repulsion (all pairs, or use approximate neighbors for large n)
        for i in range(n):
            for j in range(n):
                if i == j:
                    continue
                delta = pos[i] - pos[j]
                d = float(np.linalg.norm(delta)) + 1e-9
                disp[i] += (delta / d) * (k * k / d)
        # Attraction along edges
        if edge_index.size >= 2:
            for e in range(edge_index.shape[1]):
                i, j = int(edge_index[0, e]), int(edge_index[1, e])
                if i < 0 or j < 0 or i >= n or j >= n:
                    continue
                delta = pos[j] - pos[i]
                d = float(np.linalg.norm(delta)) + 1e-9
                disp[i] -= (delta / d) * (d * d / k)
                disp[j] += (delta / d) * (d * d / k)
        pos += disp * 0.1
    return pos


def layout_fruchterman_reingold_nx(
    node_ids: list[str],
    edges: list[tuple[str, str]],
    current_positions: dict[str, np.ndarray] | None = None,
    *,
    iterations: int = 50,
    dim: int = 2,
) -> np.ndarray:
    """
    Fruchterman-Reingold via NetworkX (spring_layout with F-R style). Returns positions (n, dim) in node_ids order.
    """
    import networkx as nx
    G = nx.Graph()
    G.add_nodes_from(node_ids)
    G.add_edges_from(edges)
    pos_map = nx.spring_layout(
        G, pos=current_positions, dim=dim, iterations=iterations,
        seed=42,
    )
    return np.array([pos_map[nid] if nid in pos_map else np.zeros(dim) for nid in node_ids], dtype=np.float32)


def layout_som(
    positions: np.ndarray,
    *,
    grid_shape: tuple[int, int] = (10, 10),
    sigma: float = 1.0,
    lr: float = 0.5,
    iterations: int = 100,
) -> np.ndarray:
    """
    Self-organizing map (MiniSom) layout: map nodes to 2D grid, return 2D positions.
    positions (n, dim) used as input features; output (n, 2) in [0,1] x [0,1].
    """
    n, dim = positions.shape
    if n == 0:
        return positions[:, :2] if positions.shape[1] >= 2 else np.zeros((0, 2), dtype=np.float32)
    try:
        from minisom import MiniSom
    except ImportError:
        logger.warning("MiniSom not installed; returning original positions truncated to 2D")
        return np.asarray(positions[:, :2], dtype=np.float32)
    som = MiniSom(
        grid_shape[0], grid_shape[1], dim,
        sigma=sigma, learning_rate=lr, random_seed=42,
    )
    som.train(positions, iterations, verbose=False)
    out = np.zeros((n, 2), dtype=np.float32)
    for i in range(n):
        win = som.winner(positions[i])
        out[i, 0] = (win[0] + 0.5) / grid_shape[0]
        out[i, 1] = (win[1] + 0.5) / grid_shape[1]
    return out

