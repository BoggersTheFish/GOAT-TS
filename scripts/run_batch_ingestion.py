"""
Phase 2: Batch ingestion – acquire dumps, optional Spark ETL, then extraction into graph.

Runs:
  1. Acquire dumps (if --acquire and input missing) to data/raw/wikipedia/abstracts.txt.
  2. Optional Spark ETL: convert text to parquet at data/processed/corpus.parquet (if --spark-etl).
  3. Extraction pipeline on the chosen input (txt or parquet) and insert into NebulaGraph (if --live).

Usage (from repo root):
  python scripts/run_batch_ingestion.py --acquire --live
  python scripts/run_batch_ingestion.py --input-path data/processed/corpus.parquet --live
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _run(cmd: list[str], timeout: int = 600) -> tuple[int, str, str]:
    r = subprocess.run(
        cmd,
        cwd=ROOT,
        env={**__import__("os").environ, "PYTHONPATH": str(ROOT)},
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    return r.returncode, (r.stdout or "").strip(), (r.stderr or "").strip()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Phase 2: Acquire dumps, optional Spark ETL, batch extraction/insertion."
    )
    parser.add_argument(
        "--acquire",
        action="store_true",
        help="Run acquire_dumps first if input is missing (writes data/raw/wikipedia/abstracts.txt).",
    )
    parser.add_argument(
        "--spark-etl",
        action="store_true",
        help="Run Spark ETL to convert text to parquet before extraction.",
    )
    parser.add_argument(
        "--input-path",
        type=Path,
        default=None,
        help="Input text or parquet path. Default: data/processed/corpus.parquet if --spark-etl else data/raw/wikipedia/abstracts.txt",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Insert into live NebulaGraph (default: dry-run).",
    )
    parser.add_argument(
        "--max-docs",
        type=int,
        default=150,
        help="Max docs when using --acquire (default 150).",
    )
    args = parser.parse_args()

    if args.spark_etl:
        default_input = ROOT / "data" / "processed" / "corpus.parquet"
        text_path = ROOT / "data" / "raw" / "wikipedia" / "abstracts.txt"
    else:
        default_input = ROOT / "data" / "raw" / "wikipedia" / "abstracts.txt"
        text_path = default_input

    input_path = args.input_path or default_input
    if not input_path.is_absolute():
        input_path = ROOT / input_path

    if args.acquire and not text_path.exists():
        (ROOT / "data" / "raw").mkdir(parents=True, exist_ok=True)
        code, out, err = _run([
            sys.executable, str(ROOT / "scripts" / "acquire_dumps.py"),
            "--output-dir", str(ROOT / "data" / "raw"),
            "--max-docs", str(args.max_docs),
        ], timeout=300)
        if code != 0:
            raise SystemExit(f"Acquire failed: {err or out}")
        print("Acquire dumps done.")

    if args.spark_etl:
        if not text_path.exists():
            raise SystemExit(f"Text input missing: {text_path}. Use --acquire first.")
        code, out, err = _run([
            sys.executable, str(ROOT / "scripts" / "run_spark_etl.py"),
            "--input-path", str(text_path),
            "--output-path", str(input_path),
        ], timeout=600)
        if code != 0:
            raise SystemExit(f"Spark ETL failed: {err or out}")
        print("Spark ETL done.")

    if not input_path.exists():
        raise SystemExit(
            f"Input path does not exist: {input_path}. "
            "Use --acquire and/or --spark-etl, or set --input-path."
        )

    code, out, err = _run([
        sys.executable, "-m", "src.ingestion.extraction_pipeline",
        "--input-path", str(input_path),
        *(["--live"] if args.live else []),
    ], timeout=600)
    if code != 0:
        raise SystemExit(f"Extraction failed: {err or out}")
    print(out)
    print("Batch ingestion done.")


if __name__ == "__main__":
    main()
