from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from src.graph.constraints import cosine_similarity
from src.graph.models import Edge
from src.graph.models import Node
from src.physics.forces import (
    attraction_force,
    approximate_neighbor_pairs,
    repulsion_force,
    spring_force,
)
from src.physics.simulation import integrate_step
from src.utils import load_yaml_config

# Use FAISS approximate neighbors when node count exceeds this (avoids O(n^2) death)
FAISS_FORCE_NODE_THRESHOLD = 200
FAISS_K_NEIGHBORS = 50


@dataclass(slots=True)
class SimulationState:
    node_ids: list[str]
    positions: np.ndarray
    velocities: np.ndarray
    masses: np.ndarray
    activations: np.ndarray
    embeddings: np.ndarray | None = None
    edge_pairs: list[tuple[int, int, float]] | None = None


def build_state(nodes: list[Node], dimensions: int = 3) -> SimulationState:
    node_ids = [node.node_id for node in nodes]
    positions = np.zeros((len(nodes), dimensions), dtype=np.float32)
    velocities = np.zeros((len(nodes), dimensions), dtype=np.float32)
    embeddings = []
    for index, node in enumerate(nodes):
        node_position = list(node.position)[:dimensions]
        if any(abs(float(v)) > 1.0e-9 for v in node_position):
            positions[index, : len(node_position)] = np.asarray(node_position, dtype=np.float32)
        else:
            positions[index, 0] = float(index % 97) / 97.0
            positions[index, 1] = float(index % 31) / 31.0
            positions[index, 2] = float(index % 17) / 17.0
        node_velocity = list(node.velocity)[:dimensions]
        if node_velocity:
            velocities[index, : len(node_velocity)] = np.asarray(node_velocity, dtype=np.float32)
        if node.embedding is not None:
            embeddings.append(np.asarray(node.embedding, dtype=np.float32))
        else:
            embeddings.append(np.zeros(384, dtype=np.float32))

    return SimulationState(
        node_ids=node_ids,
        positions=positions,
        velocities=velocities,
        masses=np.asarray([node.mass for node in nodes], dtype=np.float32),
        activations=np.asarray([node.activation for node in nodes], dtype=np.float32),
        embeddings=np.asarray(embeddings, dtype=np.float32) if embeddings else None,
    )


def compute_forces(
    state: SimulationState,
    edges: list[Edge] | None = None,
    config_path: str = "configs/simulation.yaml",
    *,
    use_faiss_approx: bool = True,
    faiss_k: int = FAISS_K_NEIGHBORS,
) -> np.ndarray:
    config = load_yaml_config(config_path)["simulation"]
    g_const = float(config["gravitational_constant"])
    damping = float(config["damping"])
    repulsion = float(config["repulsion"])
    epsilon = float(config["epsilon"])
    spring_constant = float(config.get("spring_constant", 0.25))
    ideal_length_base = float(config.get("ideal_spring_length_base", 1.0))
    position_bound = float(config.get("position_bound", 10.0))

    forces = np.zeros_like(state.positions, dtype=np.float32)
    index_map = {node_id: idx for idx, node_id in enumerate(state.node_ids)}
    n = len(state.node_ids)

    use_approx = use_faiss_approx and n >= FAISS_FORCE_NODE_THRESHOLD
    if use_approx:
        pairs = approximate_neighbor_pairs(state.positions, k=faiss_k, use_faiss=True)
    else:
        pairs = [(i, j) for i in range(n) for j in range(i + 1, n)]

    for src_idx, dst_idx in pairs:
        src_pos = state.positions[src_idx]
        dst_pos = state.positions[dst_idx]
        repulsive = repulsion_force(src_pos, dst_pos, repulsion_constant=repulsion, epsilon=epsilon)
        forces[src_idx] += repulsive
        forces[dst_idx] -= repulsive

        similarity = 0.0
        if state.embeddings is not None:
            similarity = cosine_similarity(state.embeddings[src_idx], state.embeddings[dst_idx])
        attractive = attraction_force(
            src_pos,
            dst_pos,
            similarity=similarity,
            attraction_constant=g_const,
            epsilon=epsilon,
        )
        forces[src_idx] += attractive
        forces[dst_idx] -= attractive

    if edges:
        for edge in edges:
            src_idx = index_map.get(edge.src_id)
            dst_idx = index_map.get(edge.dst_id)
            if src_idx is None or dst_idx is None:
                continue
            similarity = float(edge.weight)
            spring = spring_force(
                state.positions[src_idx],
                state.positions[dst_idx],
                similarity=similarity,
                spring_constant=spring_constant,
                ideal_length_base=ideal_length_base,
            )
            forces[src_idx] += spring
            forces[dst_idx] -= spring

    forces -= damping * state.positions
    state.edge_pairs = [
        (index_map[edge.src_id], index_map[edge.dst_id], float(edge.weight))
        for edge in (edges or [])
        if edge.src_id in index_map and edge.dst_id in index_map
    ]
    state.positions = np.clip(state.positions, -position_bound, position_bound)
    return forces


def update_positions(
    state: SimulationState,
    forces: np.ndarray,
    config_path: str = "configs/simulation.yaml",
    step_size: float = 0.1,
) -> SimulationState:
    config = load_yaml_config(config_path)["simulation"]
    new_positions, new_velocities = integrate_step(
        state.positions,
        state.velocities,
        forces,
        state.masses,
        dt=step_size,
        damping=float(config.get("velocity_damping", 0.96)),
        position_bound=float(config.get("position_bound", 10.0)),
    )
    return SimulationState(
        node_ids=state.node_ids,
        positions=new_positions,
        velocities=new_velocities,
        masses=state.masses.copy(),
        activations=state.activations.copy(),
        embeddings=None if state.embeddings is None else state.embeddings.copy(),
        edge_pairs=list(state.edge_pairs or []),
    )
