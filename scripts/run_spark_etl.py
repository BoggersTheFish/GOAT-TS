"""
Phase 2: Spark ETL – read text corpus and write parquet for batch extraction.

Reads a text file (one chunk per line) or a directory of text files, and writes
a parquet dataset with a 'value' column so the extraction pipeline can consume it.

Usage (from repo root):
  python scripts/run_spark_etl.py
  python scripts/run_spark_etl.py --input-path data/raw/wikipedia/abstracts.txt --output-path data/processed/corpus.parquet
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.ingestion.spark_read_dumps import build_spark_session


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Spark ETL: read text corpus, write parquet for batch extraction."
    )
    parser.add_argument(
        "--input-path",
        type=Path,
        default=ROOT / "data" / "raw" / "wikipedia" / "abstracts.txt",
        help="Input text file or directory (one chunk per line).",
    )
    parser.add_argument(
        "--output-path",
        type=Path,
        default=ROOT / "data" / "processed" / "corpus.parquet",
        help="Output parquet path (file or directory).",
    )
    parser.add_argument(
        "--partitions",
        type=int,
        default=16,
        help="Number of Spark shuffle/partition for output (default 16).",
    )
    args = parser.parse_args()

    input_path = args.input_path if args.input_path.is_absolute() else ROOT / args.input_path
    output_path = args.output_path if args.output_path.is_absolute() else ROOT / args.output_path

    if not input_path.exists():
        raise SystemExit(
            f"Input path does not exist: {input_path}. "
            "Run 'Acquire dumps' or use --source sample first (e.g. python scripts/acquire_dumps.py --source sample --output-dir data/raw)."
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    spark = build_spark_session(app_name="goat-spark-etl")
    df = spark.read.text(str(input_path)).repartition(args.partitions)
    df.write.mode("overwrite").parquet(str(output_path))
    spark.stop()
    print(f"Wrote parquet to {output_path}")


if __name__ == "__main__":
    main()
