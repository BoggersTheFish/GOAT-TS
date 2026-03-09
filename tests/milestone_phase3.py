from src.graph.models import MemoryState, Node
from src.simulation.loop import run_simulation_step


def test_phase3_simulation_updates_mass() -> None:
    nodes = [
        Node(node_id="a", label="Alpha", mass=1.0, activation=1.0, state=MemoryState.ACTIVE),
        Node(node_id="b", label="Beta", mass=1.5, activation=0.8, state=MemoryState.DORMANT),
        Node(node_id="c", label="Gamma", mass=0.9, activation=0.3, state=MemoryState.DEEP),
    ]

    updated = run_simulation_step(nodes)
    assert len(updated) == len(nodes)
    assert any(node.mass != old.mass for node, old in zip(updated, nodes))
