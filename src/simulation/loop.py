from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import networkx as nx
import numpy as np

from src.graph.client import NebulaGraphClient
from src.graph.models import Edge, MemoryState, Node
from src.simulation.gravity import build_state, compute_forces, update_positions
from src.utils import load_yaml_config


def mass_update(
    node: Node,
    force_magnitude: float,
    config: dict[str, float],
) -> Node:
    new_mass = (
        config["phi"] * node.mass
        + config["kappa"] * node.activation
        + config["lambda"] * force_magnitude
    )
    capped_mass = min(new_mass, config["max_mass"])
    new_state = node.state
    if capped_mass > config["split_threshold"]:
        new_state = MemoryState.ACTIVE

    return replace(node, mass=capped_mass, state=new_state)


def _gravity_links_for_node(
    idx: int,
    nodes: list[Node],
    edges: list[Edge],
    positions: np.ndarray,
    masses: np.ndarray,
    config: dict[str, float],
) -> dict[str, dict[str, float | str]]:
    node_id = nodes[idx].node_id
    epsilon = float(config["epsilon"])
    g_const = float(config["gravitational_constant"])
    out: dict[str, dict[str, float | str]] = {}
    index_map = {node.node_id: i for i, node in enumerate(nodes)}
    for edge in edges:
        if edge.src_id != node_id and edge.dst_id != node_id:
            continue
        other_id = edge.dst_id if edge.src_id == node_id else edge.src_id
        other_idx = index_map.get(other_id)
        if other_idx is None:
            continue
        distance = float(np.linalg.norm(positions[idx] - positions[other_idx]))
        gravity_value = (
            g_const * float(masses[idx]) * float(masses[other_idx]) * max(float(edge.weight), 0.05)
        ) / ((distance**2) + epsilon)
        out[other_id] = {
            "gravity_value": gravity_value,
            "distance": distance,
            "edge_weight": float(edge.weight),
            "relation": edge.relation,
            "linked_label": nodes[other_idx].label,
        }
    return out


def run_simulation_step(
    nodes: list[Node],
    edges: list[Edge] | None = None,
    config_path: str = "configs/simulation.yaml",
) -> list[Node]:
    config = load_yaml_config(config_path)["simulation"]
    state = build_state(nodes)
    forces = compute_forces(state, edges=edges, config_path=config_path)
    next_state = update_positions(state, forces, config_path=config_path)

    updated_nodes: list[Node] = []
    edges = edges or []
    for idx, node in enumerate(nodes):
        magnitude = float(np.linalg.norm(forces[idx]))
        gravity_links = _gravity_links_for_node(
            idx,
            nodes,
            edges,
            next_state.positions,
            next_state.masses,
            config,
        )
        gravity_neighbors = sorted(
            (
                {"node_id": other_id, **details}
                for other_id, details in gravity_links.items()
            ),
            key=lambda item: float(item["gravity_value"]),
            reverse=True,
        )
        metadata = dict(node.metadata)
        metadata["gravity_profile"] = {
            "force_magnitude": magnitude,
            "mass": float(next_state.masses[idx]),
            "activation": float(next_state.activations[idx]),
            "position": next_state.positions[idx].astype(float).tolist(),
            "velocity": next_state.velocities[idx].astype(float).tolist(),
        }
        metadata["gravity_links"] = gravity_links
        metadata["gravity_neighbors"] = gravity_neighbors[:12]
        updated_nodes.append(
            replace(
                mass_update(node, magnitude, config),
                position=next_state.positions[idx].astype(float).tolist(),
                velocity=next_state.velocities[idx].astype(float).tolist(),
                metadata=metadata,
            )
        )
    return updated_nodes


def detect_domains(nodes: list[Node], edges: list[tuple[str, str]]) -> dict[str, int]:
    graph = nx.Graph()
    graph.add_nodes_from(node.node_id for node in nodes)
    graph.add_edges_from(edges)
    communities = nx.community.louvain_communities(graph, seed=42)

    domain_map: dict[str, int] = {}
    for idx, community in enumerate(communities):
        for node_id in community:
            domain_map[node_id] = idx
    return domain_map


def run_from_graph(
    config_root: Path,
    live: bool = False,
    node_limit: int = 250,
    edge_limit: int = 2000,
) -> dict[str, int]:
    client = NebulaGraphClient(
        config_root / "configs" / "graph.yaml",
        dry_run_override=not live if live else None,
    )
    # Edge-first snapshot so we get a connected subgraph (relates edges only; wave nodes are excluded).
    snapshot = client.snapshot_induced_by_edges(edge_limit=edge_limit)
    nodes = [
        Node(
            node_id=node["node_id"],
            label=node["label"],
            mass=node["mass"],
            activation=node["activation"],
            state=MemoryState(node["state"]),
            cluster_id=node["cluster_id"] or None,
            embedding=node.get("embedding"),
            position=node.get("position", [0.0, 0.0, 0.0]),
            velocity=node.get("velocity", [0.0, 0.0, 0.0]),
            attention_weight=node.get("attention_weight", 0.0),
            created_at=node.get("created_at") or Node(node_id="tmp", label="tmp").created_at,
            metadata=node["metadata"],
        )
        for node in snapshot["nodes"]
    ]
    edge_models = [
        Edge(
            src_id=edge["src_id"],
            dst_id=edge["dst_id"],
            relation=edge.get("relation", "relates"),
            weight=edge.get("weight", 1.0),
            metadata=edge.get("metadata", {}),
        )
        for edge in snapshot["edges"]
    ]
    updated_nodes = run_simulation_step(nodes, edge_models, config_root / "configs" / "simulation.yaml")
    edge_pairs = [(edge["src_id"], edge["dst_id"]) for edge in snapshot["edges"]]
    domains = detect_domains(updated_nodes, edge_pairs) if edge_pairs else {}

    if live and updated_nodes:
        from tqdm import tqdm
        progress_interval = max(1, min(500, len(updated_nodes) // 20))
        with tqdm(total=len(updated_nodes), unit="nodes", desc="Persisting to graph") as pbar:
            def on_progress(current: int, total: int) -> None:
                pbar.n = current
                pbar.refresh()
            client.update_nodes(
                updated_nodes,
                domain_map=domains,
                on_progress=on_progress,
                progress_interval=progress_interval,
            )

    client.close()
    return {
        "updated_nodes": len(updated_nodes),
        "domains": len(set(domains.values())),
        "source_nodes": len(snapshot["nodes"]),
        "source_edges": len(snapshot["edges"]),
        "live": live,
    }
