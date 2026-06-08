"""Simple deterministic spreading activation."""

from __future__ import annotations

from goat_ts.core.graph import InMemoryGraph


def spread_activation(
    graph: InMemoryGraph,
    seed_ids: tuple[str, ...],
    *,
    steps: int = 2,
    decay: float = 0.5,
) -> dict[str, float]:
    for node in graph.nodes.values():
        node.activation = 0.0

    frontier = {node_id: 1.0 for node_id in seed_ids if node_id in graph.nodes}
    for _ in range(steps + 1):
        next_frontier: dict[str, float] = {}
        for source_id in sorted(frontier):
            strength = frontier[source_id]
            graph.nodes[source_id].activation = max(
                graph.nodes[source_id].activation, strength
            )
            for target_id in graph.neighbors(source_id):
                propagated = round(strength * decay, 6)
                next_frontier[target_id] = max(
                    next_frontier.get(target_id, 0.0), propagated
                )
        frontier = next_frontier
    return {
        node.id: node.activation
        for node in graph.sorted_nodes()
        if node.activation > 0.0
    }
