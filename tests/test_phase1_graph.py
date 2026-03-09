from pathlib import Path

from src.graph.client import NebulaGraphClient
from src.graph.models import Edge, MemoryState, Node


def test_graph_client_dry_run_insert_and_query() -> None:
    root = Path(__file__).resolve().parents[1]
    client = NebulaGraphClient(root / "configs" / "graph.yaml")
    client.insert_nodes(
        [
            Node(node_id="a", label="Alpha", state=MemoryState.ACTIVE),
            Node(node_id="b", label="Beta", state=MemoryState.DORMANT),
        ]
    )
    client.insert_edges([Edge(src_id="a", dst_id="b", weight=0.8)])

    assert client.get_node("a") is not None
    assert client.neighbors("a") == ["b"]
    assert len(client.search_by_state("active")) == 1
