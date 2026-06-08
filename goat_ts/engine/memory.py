"""Memory-state transitions derived from activation."""

from __future__ import annotations

from goat_ts.core.graph import InMemoryGraph


def transition_memory(
    graph: InMemoryGraph,
    *,
    active_threshold: float = 0.6,
    dormant_threshold: float = 0.2,
) -> dict[str, str]:
    for node in graph.nodes.values():
        if node.activation >= active_threshold:
            node.memory_state = "active"
        elif node.activation >= dormant_threshold:
            node.memory_state = "dormant"
        else:
            node.memory_state = "deep"
    return {node.id: node.memory_state for node in graph.sorted_nodes()}
