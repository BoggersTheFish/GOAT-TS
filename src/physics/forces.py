from __future__ import annotations

import numpy as np


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

