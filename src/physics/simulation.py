from __future__ import annotations

import numpy as np


def integrate_step(
    positions: np.ndarray,
    velocities: np.ndarray,
    forces: np.ndarray,
    masses: np.ndarray,
    dt: float,
    damping: float,
    position_bound: float | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    safe_masses = np.maximum(masses.reshape(-1, 1), 1.0e-6)
    accelerations = forces / safe_masses
    new_velocities = (velocities + accelerations * dt) * damping
    new_positions = positions + new_velocities * dt
    if position_bound is not None:
        new_positions = np.clip(new_positions, -position_bound, position_bound)
    return new_positions.astype(np.float32), new_velocities.astype(np.float32)

