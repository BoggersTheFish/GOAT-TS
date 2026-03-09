from pathlib import Path

from src.ingestion.llm_extract import TripleExtractor


def test_regex_fallback_extracts_basic_triples() -> None:
    root = Path(__file__).resolve().parents[1]
    extractor = TripleExtractor(root / "configs" / "llm.yaml")
    result = extractor.extract("Wikipedia is a free encyclopedia. NebulaGraph supports graph queries.")

    assert result.triples
    assert any(triple.subject == "Wikipedia" for triple in result.triples)
