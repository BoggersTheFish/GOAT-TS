from pathlib import Path

from src.reasoning.loop import run_reasoning_loop


def test_phase4_reasoning_generates_hypotheses() -> None:
    root = Path(__file__).resolve().parents[1]
    response = run_reasoning_loop(
        "Wikipedia supports structured facts and Wikidata supports knowledge graphs.",
        root,
    )

    assert response.query
    assert response.tension.score >= 0.0
    assert isinstance(response.hypotheses, list)
