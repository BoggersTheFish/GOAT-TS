from __future__ import annotations

import numpy as np


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    va = np.asarray(a, dtype=np.float32)
    vb = np.asarray(b, dtype=np.float32)
    denom = np.linalg.norm(va) * np.linalg.norm(vb)
    if denom == 0.0:
        return 0.0
    return float(np.dot(va, vb) / denom)


def knn_edges(
    node_ids: list[str],
    embeddings: np.ndarray,
    max_edges_per_node: int,
    similarity_threshold: float,
) -> list[tuple[str, str, float]]:
    if len(node_ids) <= 1:
        return []

    edges: list[tuple[str, str, float]] = []
    for idx, node_id in enumerate(node_ids):
        scores: list[tuple[float, str]] = []
        for jdx, other_id in enumerate(node_ids):
            if idx == jdx:
                continue
            sim = cosine_similarity(embeddings[idx], embeddings[jdx])
            if sim >= similarity_threshold:
                scores.append((sim, other_id))
        scores.sort(key=lambda item: item[0], reverse=True)
        for sim, other_id in scores[:max_edges_per_node]:
            edges.append((node_id, other_id, sim))
    return edges

