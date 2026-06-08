"""Transparent mismatch scoring over graph edges."""

from __future__ import annotations

from goat_ts.core.graph import InMemoryGraph


def score_tension(graph: InMemoryGraph) -> dict[str, float]:
    return {
        edge.id: round(
            abs(
                graph.nodes[edge.source_id].activation
                - graph.nodes[edge.target_id].activation
            ),
            6,
        )
        for edge in graph.sorted_edges()
    }
