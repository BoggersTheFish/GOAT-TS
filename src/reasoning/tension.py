from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(slots=True)
class TensionResult:
    score: float
    high_tension_pairs: list[tuple[str, str, float]]


def compute_tension(
    positions: dict[str, np.ndarray],
    expected_distances: dict[tuple[str, str], float],
) -> TensionResult:
    total = 0.0
    pairs: list[tuple[str, str, float]] = []

    for (src, dst), expected_distance in expected_distances.items():
        actual_distance = float(np.linalg.norm(positions[src] - positions[dst]))
        delta = (actual_distance - expected_distance) ** 2
        total += delta
        pairs.append((src, dst, delta))

    pairs.sort(key=lambda item: item[2], reverse=True)
    return TensionResult(score=total, high_tension_pairs=pairs[:10])
