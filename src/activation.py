"""
Spreading activation over the concept graph. ACT-R inspired: damped iteration,
fan-out limit (max hops), threshold cutoff. Uses PyTorch tensors for batched
propagation (CPU/GPU). Core of TS wave propagation: activate(seeds) → propagate → subgraph.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from typing import Optional

import numpy as np

from src.graph.models import Edge, Node

logger = logging.getLogger(__name__)

# Defaults (ACT-R style)
DEFAULT_DECAY = 0.1
DEFAULT_THRESHOLD = 0.1
DEFAULT_MAX_HOPS = 5
DEFAULT_BIAS = 0.0


@dataclass(slots=True)
class PropagationResult:
    """Result of spreading activation: activations per node_id, and number of iterations."""
    activations: dict[str, float]
    iterations: int
    converged: bool


def _build_adjacency(
    node_ids: list[str],
    edges: list[Edge],
    relation: str = "relates",
) -> tuple[np.ndarray, np.ndarray]:
    """
    Build weighted adjacency matrix (n x n) and in-degree style matrix for propagation.
    Returns (adj, adj_transpose) as float32 arrays; adj[i,j] = weight from j -> i (so row i = incoming to i).
    """
    n = len(node_ids)
    id_to_idx = {nid: i for i, nid in enumerate(node_ids)}
    adj = np.zeros((n, n), dtype=np.float32)
    for e in edges:
        if e.relation != relation:
            continue
        i = id_to_idx.get(e.src_id)
        j = id_to_idx.get(e.dst_id)
        if i is not None and j is not None:
            # activation flows src -> dst: so dst receives from src
            adj[j, i] = max(adj[j, i], float(e.weight))
            adj[i, j] = max(adj[i, j], float(e.weight))  # undirected
    return adj, adj.T


def propagate_spreading_activation(
    node_ids: list[str],
    edges: list[Edge],
    seed_ids: list[str],
    *,
    max_hops: int = DEFAULT_MAX_HOPS,
    decay: float = DEFAULT_DECAY,
    threshold: float = DEFAULT_THRESHOLD,
    bias: float = DEFAULT_BIAS,
    initial_activation: float = 1.0,
    use_torch: bool = True,
) -> PropagationResult:
    """
    ACT-R style spreading activation: act_{t+1} = sum(incoming * weight) * (1 - decay) + bias.
    Seeds get initial_activation (1.0). Propagation stops after max_hops or when converged.
    Activations below threshold are set to 0 (and not propagated further in effect).
    """
    if not node_ids:
        return PropagationResult(activations={}, iterations=0, converged=True)
    id_to_idx = {nid: i for i, nid in enumerate(node_ids)}
    adj, _ = _build_adjacency(node_ids, edges)
    n = len(node_ids)

    try:
        import torch
    except ImportError:
        use_torch = False
    iterations = 0
    if use_torch:
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        adj_t = torch.from_numpy(adj).to(device)
        act = torch.zeros(n, dtype=torch.float32, device=device)
        for sid in seed_ids:
            idx = id_to_idx.get(sid)
            if idx is not None:
                act[idx] = initial_activation
        for iterations in range(1, max_hops + 1):
            act_prev = act.clone()
            act = (adj_t @ act) * (1.0 - decay) + bias
            for sid in seed_ids:
                idx = id_to_idx.get(sid)
                if idx is not None:
                    act[idx] = max(act[idx].item(), initial_activation)
            act[act < threshold] = 0.0
            if torch.allclose(act, act_prev, atol=1e-6):
                break
        activations = {node_ids[i]: float(act[i].item()) for i in range(n)}
    else:
        act = np.zeros(n, dtype=np.float32)
        for sid in seed_ids:
            idx = id_to_idx.get(sid)
            if idx is not None:
                act[idx] = initial_activation
        for iterations in range(1, max_hops + 1):
            act_prev = act.copy()
            act = (adj @ act) * (1.0 - decay) + bias
            for sid in seed_ids:
                idx = id_to_idx.get(sid)
                if idx is not None:
                    act[idx] = max(act[idx], initial_activation)
            act[act < threshold] = 0.0
            if np.allclose(act, act_prev, atol=1e-6):
                break
        activations = {node_ids[i]: float(act[i]) for i in range(n)}

    converged = iterations < max_hops
    return PropagationResult(activations=activations, iterations=iterations, converged=converged)


def apply_activations_to_nodes(
    nodes: list[Node],
    activations: dict[str, float],
) -> list[Node]:
    """Return new nodes with activation values updated from the activations dict."""
    out = []
    for n in nodes:
        a = activations.get(n.node_id, n.activation)
        out.append(replace(n, activation=float(a)))
    return out


def activate_and_propagate(
    nodes: list[Node],
    edges: list[Edge],
    seed_node_ids: list[str],
    *,
    max_hops: int = DEFAULT_MAX_HOPS,
    decay: float = DEFAULT_DECAY,
    threshold: float = DEFAULT_THRESHOLD,
    bias: float = DEFAULT_BIAS,
) -> tuple[list[Node], PropagationResult]:
    """
    Run spreading activation and return (updated nodes with new activations, result).
    Seeds are boosted to 1.0; propagation runs over relates edges with fan-out limit.
    """
    node_ids = [n.node_id for n in nodes]
    result = propagate_spreading_activation(
        node_ids, edges, seed_node_ids,
        max_hops=max_hops, decay=decay, threshold=threshold, bias=bias,
    )
    updated = apply_activations_to_nodes(nodes, result.activations)
    return updated, result


def get_activated_subgraph(
    nodes: list[Node],
    edges: list[Edge],
    seed_node_ids: list[str],
    *,
    min_activation: float = DEFAULT_THRESHOLD,
    max_hops: int = DEFAULT_MAX_HOPS,
    decay: float = DEFAULT_DECAY,
) -> tuple[list[Node], list[Edge], PropagationResult]:
    """
    Run spreading activation and return (activated nodes, induced edges, result).
    Only nodes with activation >= min_activation are kept; edges between them retained.
    """
    updated, result = activate_and_propagate(
        nodes, edges, seed_node_ids,
        max_hops=max_hops, decay=decay, threshold=min_activation,
    )
    active_ids = {nid for nid, a in result.activations.items() if a >= min_activation}
    out_nodes = [n for n in updated if n.node_id in active_ids]
    out_edges = [e for e in edges if e.src_id in active_ids and e.dst_id in active_ids]
    return out_nodes, out_edges, result
