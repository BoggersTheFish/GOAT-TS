from __future__ import annotations

from collections import Counter

from src.graph.models import Edge, MemoryState, Node


def initialize_memory_states(nodes: list[Node], edges: list[Edge]) -> list[Node]:
    degree_counter: Counter[str] = Counter()
    for edge in edges:
        degree_counter[edge.src_id] += 1
        degree_counter[edge.dst_id] += 1

    if not nodes:
        return []

    max_degree = max(degree_counter.values(), default=1)
    ranked = sorted(nodes, key=lambda node: degree_counter[node.node_id], reverse=True)
    active_cutoff = max(1, len(ranked) // 10)
    dormant_cutoff = max(1, len(ranked) // 2)

    updated_nodes: list[Node] = []
    for index, node in enumerate(ranked):
        normalized_degree = degree_counter[node.node_id] / max_degree
        if index < active_cutoff:
            state = MemoryState.ACTIVE
        elif index < dormant_cutoff:
            state = MemoryState.DORMANT
        else:
            state = MemoryState.DEEP

        updated_nodes.append(
            Node(
                node_id=node.node_id,
                label=node.label,
                mass=max(node.mass, 0.5 + normalized_degree),
                activation=max(node.activation, normalized_degree),
                state=state,
                cluster_id=node.cluster_id,
                metadata=node.metadata,
            )
        )
    return updated_nodes
