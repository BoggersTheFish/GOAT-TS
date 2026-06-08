import json

from goat_ts.cli import run_demo
from goat_ts.core.graph import InMemoryGraph
from goat_ts.core.ids import deterministic_id, node_id, wave_id
from goat_ts.core.models import CandidateClaim, Receipt, Wave
from goat_ts.engine.activation import spread_activation
from goat_ts.engine.memory import transition_memory
from goat_ts.engine.tension import score_tension
from goat_ts.ingest.parser import parse_text
from goat_ts.receipts.writer import receipt_json, write_receipt


def make_wave() -> Wave:
    return Wave(id=wave_id("test", "Alpha uses Beta"), source="test", content_hash="abc")


def make_claim(subject: str = "Alpha", object_: str = "Beta") -> CandidateClaim:
    return CandidateClaim(
        id=deterministic_id("claim", subject, "uses", object_),
        subject=subject,
        predicate="uses",
        object=object_,
        raw_text=f"{subject} uses {object_}",
    )


def test_deterministic_ids_are_stable_and_uuid_shaped():
    first = deterministic_id("node", "alpha")
    assert first == deterministic_id("node", "alpha")
    assert first != deterministic_id("node", "beta")
    assert [len(part) for part in first.split("-")] == [8, 4, 4, 4, 12]
    assert node_id(" Alpha  Node ") == node_id("alpha node")


def test_parser_creates_candidates_and_repairs():
    candidates, repairs = parse_text(
        "Alpha is Beta.\nGamma HAS Delta\nAlpha contradicts Beta\n"
    )
    assert [(item.subject, item.predicate, item.object) for item in candidates] == [
        ("Alpha", "is", "Beta"),
        ("Gamma", "has", "Delta"),
    ]
    assert len(repairs) == 1
    assert repairs[0].reason == "unsupported_or_failed_parse"
    assert repairs[0].raw_text == "Alpha contradicts Beta"


def test_graph_insert_requires_and_records_wave_provenance():
    graph = InMemoryGraph()
    wave = make_wave()
    edge = graph.insert_claim(make_claim(), wave)
    assert edge.wave_id == wave.id
    assert wave.id in edge.provenance
    assert all(node.provenance == (wave.id,) for node in graph.nodes.values())


def test_duplicate_graph_insert_accumulates_claim_provenance():
    graph = InMemoryGraph()
    wave = make_wave()
    first = make_claim()
    second = CandidateClaim(
        id=deterministic_id("claim", "second observation"),
        subject=first.subject,
        predicate=first.predicate,
        object=first.object,
        raw_text=first.raw_text,
    )
    graph.insert_claim(first, wave)
    edge = graph.insert_claim(second, wave)
    assert first.id in edge.provenance
    assert second.id in edge.provenance
    assert wave.id in edge.provenance


def test_activation_spreads_deterministically():
    graph = InMemoryGraph()
    graph.insert_claim(make_claim(), make_wave())
    values = spread_activation(graph, (node_id("Alpha"),), steps=1, decay=0.5)
    assert values == {node_id("Alpha"): 1.0, node_id("Beta"): 0.5}


def test_memory_transitions_follow_activation_thresholds():
    graph = InMemoryGraph()
    wave = make_wave()
    graph.insert_claim(make_claim(), wave)
    graph.insert_claim(make_claim("Beta", "Gamma"), wave)
    spread_activation(graph, (node_id("Alpha"),), steps=1, decay=0.5)
    states = transition_memory(graph)
    assert states[node_id("Alpha")] == "active"
    assert states[node_id("Beta")] == "dormant"
    assert states[node_id("Gamma")] == "deep"


def test_tension_is_activation_mismatch():
    graph = InMemoryGraph()
    edge = graph.insert_claim(make_claim(), make_wave())
    graph.nodes[edge.source_id].activation = 1.0
    graph.nodes[edge.target_id].activation = 0.25
    assert score_tension(graph) == {edge.id: 0.75}


def test_receipt_writing_is_deterministic(tmp_path):
    receipt = Receipt(
        id="receipt-id",
        version="0.1.0",
        operation="test",
        input={"b": 2, "a": 1},
    )
    first = write_receipt(receipt, tmp_path / "first.json").read_text()
    second = write_receipt(receipt, tmp_path / "second.json").read_text()
    assert first == second == receipt_json(receipt)
    assert json.loads(first)["input"] == {"a": 1, "b": 2}


def test_demo_writes_same_receipt_and_exposes_repair_target(tmp_path):
    input_path = tmp_path / "sample.txt"
    input_path.write_text("Alpha uses Beta\nAlpha maybe Beta\n", encoding="utf-8")
    first_path = tmp_path / "first.json"
    second_path = tmp_path / "second.json"
    first = run_demo(input_path, first_path)
    second = run_demo(input_path, second_path)
    assert first.id == second.id
    assert first_path.read_bytes() == second_path.read_bytes()
    assert len(first.repair_targets) == 1
