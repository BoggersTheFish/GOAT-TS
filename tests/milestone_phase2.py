import subprocess
import sys
from pathlib import Path

import pytest

from src.ingestion.extraction_pipeline import (
    _read_texts_from_path,
    extract_from_texts,
    load_into_graph,
)


def test_phase2_extraction_pipeline_builds_graph_payload() -> None:
    root = Path(__file__).resolve().parents[1]
    texts = [
        "Wikipedia is a free encyclopedia.",
        "Wikidata supports structured knowledge.",
    ]
    nodes, edges, waves, in_wave_edges = extract_from_texts(texts, root)

    assert len(nodes) >= 2
    assert len(edges) >= 2
    assert len(waves) >= 1
    assert len(in_wave_edges) >= 1


def test_phase2_acquire_dumps_produces_file() -> None:
    """Phase 2: dump acquisition writes abstracts.txt."""
    root = Path(__file__).resolve().parents[1]
    out_dir = root / "data" / "raw" / "wikipedia"
    out_dir.mkdir(parents=True, exist_ok=True)
    code = subprocess.run(
        [
            sys.executable,
            str(root / "scripts" / "acquire_dumps.py"),
            "--output-dir",
            str(root / "data" / "raw"),
            "--source",
            "sample",
            "--max-docs",
            "5",
        ],
        cwd=root,
        env={**__import__("os").environ, "PYTHONPATH": str(root)},
        capture_output=True,
        text=True,
        timeout=30,
    ).returncode
    assert code == 0
    abstracts = root / "data" / "raw" / "wikipedia" / "abstracts.txt"
    assert abstracts.exists()
    lines = [ln.strip() for ln in abstracts.read_text().splitlines() if ln.strip()]
    assert len(lines) >= 5


@pytest.mark.skipif(
    __import__("importlib").util.find_spec("pyarrow") is None,
    reason="pyarrow required for parquet test",
)
def test_phase2_extraction_from_parquet() -> None:
    """Phase 2: extraction pipeline reads parquet with 'value' column and loads graph (dry-run)."""
    import tempfile
    import pyarrow as pa
    import pyarrow.parquet as pq

    root = Path(__file__).resolve().parents[1]
    with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as f:
        parquet_path = Path(f.name)
    try:
        table = pa.Table.from_pydict({
            "value": [
                "Wikipedia is a free encyclopedia.",
                "NebulaGraph supports graph analytics.",
            ]
        })
        pq.write_table(table, parquet_path)
        texts = _read_texts_from_path(parquet_path)
        assert len(texts) >= 2
        stats = load_into_graph(
            iter(texts),
            root,
            live=False,
        )
        assert stats["nodes"] >= 2
        assert stats["edges"] >= 2
    finally:
        parquet_path.unlink(missing_ok=True)


@pytest.mark.skipif(
    __import__("importlib").util.find_spec("pyarrow") is None,
    reason="pyarrow required to assert parquet output",
)
@pytest.mark.skipif(
    not __import__("os").environ.get("JAVA_HOME"),
    reason="JAVA_HOME required for Spark ETL",
)
def test_phase2_spark_etl_produces_parquet() -> None:
    """Phase 2: Spark ETL reads text and writes parquet with 'value' column."""
    import tempfile
    import pyarrow.parquet as pq

    root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory() as tmp:
        txt = Path(tmp) / "chunks.txt"
        txt.write_text("Wikipedia is an encyclopedia.\nNebulaGraph is a graph database.\n")
        out = Path(tmp) / "out.parquet"
        result = subprocess.run(
            [
                sys.executable,
                str(root / "scripts" / "run_spark_etl.py"),
                "--input-path",
                str(txt),
                "--output-path",
                str(out),
                "--partitions",
                "2",
            ],
            cwd=root,
            env={**__import__("os").environ, "PYTHONPATH": str(root)},
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            pytest.fail(f"Spark ETL failed: {result.stderr or result.stdout}")
        # Spark writes a directory of part-*.parquet files
        assert out.exists()
        if out.is_dir():
            files = list(out.glob("*.parquet"))
            assert files
            tbl = pq.read_table(files[0])
        else:
            tbl = pq.read_table(out)
        assert "value" in tbl.column_names
        assert len(tbl) >= 2
