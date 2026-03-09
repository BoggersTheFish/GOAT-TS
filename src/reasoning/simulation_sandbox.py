"""
Internal simulation: clone subgraphs, apply hypotheticals without modifying the main graph.
Use for "what-if" reasoning (e.g. what if node X had higher activation?).
"""
from __future__ import annotations

import logging
from dataclasses import replace

from src.activation import activate_and_propagate
from src.graph.models import Edge, Node

logger = logging.getLogger(__name__)


def clone_subgraph(
    nodes: list[Node],
    edges: list[Edge],
    node_ids: set[str] | None = None,
    *,
    include_induced_edges: bool = True,
) -> tuple[list[Node], list[Edge]]:
    """
    Deep-copy a subgraph. If node_ids is None, clone all nodes/edges.
    If node_ids is set, clone only those nodes and (if include_induced_edges) edges between them.
    """
    if node_ids is None:
        node_ids = {n.node_id for n in nodes}
    id_set = set(node_ids)
    nodes_copy = [replace(n) for n in nodes if n.node_id in id_set]
    if not include_induced_edges:
        return nodes_copy, []
    edges_copy = [
        Edge(src_id=e.src_id, dst_id=e.dst_id, relation=e.relation, weight=e.weight, metadata=dict(e.metadata))
        for e in edges
        if e.src_id in id_set and e.dst_id in id_set
    ]
    return nodes_copy, edges_copy


def apply_hypothetical_activations(
    nodes: list[Node],
    overrides: dict[str, float],
) -> list[Node]:
    """Return new nodes with activation overrides applied (node_id -> activation)."""
    overrides_set = set(overrides)
    return [
        replace(n, activation=overrides[n.node_id]) if n.node_id in overrides_set else replace(n)
        for n in nodes
    ]


def apply_hypothetical_positions(
    nodes: list[Node],
    overrides: dict[str, list[float]],
) -> list[Node]:
    """Return new nodes with position overrides applied (node_id -> [x,y,z])."""
    overrides_set = set(overrides)
    return [
        replace(n, position=list(overrides[n.node_id])) if n.node_id in overrides_set else replace(n)
        for n in nodes
    ]


def run_sandbox_propagation(
    nodes: list[Node],
    edges: list[Edge],
    seed_ids: list[str],
    *,
    hypothetical_activations: dict[str, float] | None = None,
    max_hops: int = 5,
    decay: float = 0.1,
    threshold: float = 0.1,
) -> tuple[list[Node], dict[str, float]]:
    """
    Run spreading activation in a sandbox. Optionally apply hypothetical seed activations
    (overrides for seed_ids). Returns (updated sandbox nodes, activations dict).
    Does not modify the input lists.
    """
    sandbox_nodes, sandbox_edges = clone_subgraph(nodes, edges, node_ids=None)
    if hypothetical_activations:
        sandbox_nodes = apply_hypothetical_activations(sandbox_nodes, hypothetical_activations)
    updated, result = activate_and_propagate(
        sandbox_nodes,
        sandbox_edges,
        seed_ids,
        max_hops=max_hops,
        decay=decay,
        threshold=threshold,
    )
    return updated, result.activations


def run_sandbox_hypothetical(
    nodes: list[Node],
    edges: list[Edge],
    *,
    activation_overrides: dict[str, float] | None = None,
    position_overrides: dict[str, list[float]] | None = None,
    seed_ids: list[str] | None = None,
    run_propagation: bool = True,
    max_hops: int = 5,
) -> tuple[list[Node], list[Edge], dict[str, float] | None]:
    """
    Clone full subgraph, apply hypothetical activations/positions, optionally run propagation.
    Returns (sandbox nodes, sandbox edges, activations or None if run_propagation=False).
    """
    sandbox_nodes, sandbox_edges = clone_subgraph(nodes, edges)
    if activation_overrides:
        sandbox_nodes = apply_hypothetical_activations(sandbox_nodes, activation_overrides)
    if position_overrides:
        sandbox_nodes = apply_hypothetical_positions(sandbox_nodes, position_overrides)

    activations: dict[str, float] | None = None
    if run_propagation and seed_ids:
        sandbox_nodes, result = activate_and_propagate(
            sandbox_nodes, sandbox_edges, seed_ids, max_hops=max_hops
        )
        activations = result.activations
    return sandbox_nodes, sandbox_edges, activations
