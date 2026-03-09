from __future__ import annotations

from src.graph.models import Edge, MemoryState, Node
from src.simulation.loop import run_simulation_step


def test_gravity_simulation_updates_position_and_mass() -> None:
    nodes = [
        Node(
            node_id="a",
            label="gravity",
            mass=1.0,
            activation=1.0,
            state=MemoryState.ACTIVE,
            embedding=[1.0, 0.0, 0.0],
            position=[0.0, 0.0, 0.0],
        ),
        Node(
            node_id="b",
            label="mass",
            mass=1.5,
            activation=0.8,
            state=MemoryState.DORMANT,
            embedding=[0.9, 0.1, 0.0],
            position=[1.0, 0.0, 0.0],
        ),
    ]
    edges = [Edge(src_id="a", dst_id="b", weight=0.9)]

    updated = run_simulation_step(nodes, edges)

    assert len(updated) == 2
    assert any(node.mass != old.mass for node, old in zip(updated, nodes))
    assert any(node.position != old.position for node, old in zip(updated, nodes))
    assert "gravity_links" in updated[0].metadata
    assert updated[0].metadata["gravity_neighbors"]

