from pathlib import Path

from src.graph.client import NebulaGraphClient
from src.graph.cognition import EDGE_IN_WAVE, WAVE_SOURCE_INGESTION
from src.graph.models import Edge, MemoryState, Node, Wave
from src.ingestion.extraction_pipeline import extract_from_texts, load_into_graph


def test_phase1_local_stack_interfaces() -> None:
    root = Path(__file__).resolve().parents[1]
    stats = load_into_graph(
        [
            "Wikipedia is a free encyclopedia.",
            "NebulaGraph supports graph analytics.",
        ],
        root,
    )
    client = NebulaGraphClient(root / "configs" / "graph.yaml")

    assert stats["nodes"] >= 2
    assert stats["edges"] >= 2
    assert stats.get("waves", 0) >= 1
    assert stats.get("in_wave_edges", 0) >= 1
    assert client.dry_run is True


def test_phase1_cognition_graph_extraction_emits_waves_and_in_wave_edges() -> None:
    root = Path(__file__).resolve().parents[1]
    nodes, edges, waves, in_wave_edges = extract_from_texts(
        ["Wikipedia is a free encyclopedia.", "NebulaGraph supports graph analytics."],
        root,
        use_clusters=True,
    )
    assert len(waves) >= 1
    assert len(in_wave_edges) >= 1
    assert all(e.relation == EDGE_IN_WAVE for e in in_wave_edges)
    assert all(w.source == WAVE_SOURCE_INGESTION for w in waves)


def test_phase1_cognition_graph_client_persists_and_retrieves_waves() -> None:
    root = Path(__file__).resolve().parents[1]
    client = NebulaGraphClient(root / "configs" / "graph.yaml")
    wave = Wave(
        wave_id="wave_test_01",
        label="test wave",
        source=WAVE_SOURCE_INGESTION,
        intensity=1.0,
        coherence=0.5,
        tension=0.0,
        source_chunk_id="doc_0",
    )
    node = Node(
        node_id="concept_01",
        label="test concept",
        mass=1.0,
        activation=0.5,
        state=MemoryState.ACTIVE,
        cluster_id="",
    )
    in_wave = Edge(
        src_id=node.node_id,
        dst_id=wave.wave_id,
        relation=EDGE_IN_WAVE,
        weight=0.5,
    )
    client.insert_nodes([node])
    client.insert_waves([wave])
    client.insert_edges([in_wave])

    waves_out = client.list_waves(limit=10)
    assert len(waves_out) == 1
    assert waves_out[0].wave_id == wave.wave_id
    assert client.get_wave(wave.wave_id) is not None
    in_wave_out = client.list_in_wave_edges(limit=10)
    assert len(in_wave_out) == 1
    assert in_wave_out[0].src_id == node.node_id and in_wave_out[0].dst_id == wave.wave_id
    client.close()
