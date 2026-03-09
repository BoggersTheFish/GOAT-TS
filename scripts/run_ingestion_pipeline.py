"""
Run the full ingestion pipeline: acquire dumps -> (optional) Spark to parquet -> extract -> insert into graph.

Usage:
  python scripts/run_ingestion_pipeline.py --live
  python scripts/run_ingestion_pipeline.py --acquire --source sample --live
  python scripts/run_ingestion_pipeline.py --acquire --source wikipedia-api --max-docs 50 --live
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description="Run full ingestion: acquire -> [Spark] -> extract -> graph.")
    parser.add_argument(
        "--acquire",
        action="store_true",
        help="Run acquire_dumps first to populate data/raw.",
    )
    parser.add_argument(
        "--source",
        default="sample",
        choices=["sample", "wikipedia-api", "wikipedia-sample"],
        help="Corpus source for acquire_dumps (default: sample).",
    )
    parser.add_argument(
        "--output-dir",
        default="data/raw",
        help="Output directory for acquire_dumps.",
    )
    parser.add_argument(
        "--max-docs",
        type=int,
        default=None,
        help="Max docs for acquire (e.g. 50 for wikipedia-api).",
    )
    parser.add_argument(
        "--use-spark",
        action="store_true",
        help="Run Spark to write parquet; extraction will read from parquet.",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Insert extracted nodes/edges into live NebulaGraph.",
    )
    parser.add_argument(
        "--no-clusters",
        action="store_true",
        help="Disable cluster/topic nodes in extraction.",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    if args.acquire:
        cmd = [
            sys.executable,
            str(ROOT / "scripts" / "acquire_dumps.py"),
            "--output-dir", str(output_dir),
            "--source", args.source,
        ]
        if args.max_docs is not None:
            cmd.extend(["--max-docs", str(args.max_docs)])
        subprocess.run(cmd, check=True, cwd=str(ROOT))

    # Input for extraction: text file(s) or parquet
    if args.use_spark:
        processed_dir = output_dir.parent / "processed"
        processed_dir.mkdir(parents=True, exist_ok=True)
        parquet_path = processed_dir / "sample.parquet"
        # Spark read.text() reads a path (file or directory of text files)
        text_path = output_dir / "wikipedia" if (output_dir / "wikipedia").exists() else output_dir
        subprocess.run(
            [
                sys.executable, "-m", "src.ingestion.spark_read_dumps",
                "--input-path", str(text_path),
                "--output-path", str(parquet_path),
            ],
            check=True,
            cwd=str(ROOT),
        )
        input_path = parquet_path
    else:
        # Use text directly: abstracts.txt from acquire or sample
        input_path = output_dir / "wikipedia" / "abstracts.txt"
        if not input_path.exists():
            # Fallback: run acquire with sample if user didn't pass --acquire
            if not args.acquire:
                subprocess.run(
                    [
                        sys.executable,
                        str(ROOT / "scripts" / "acquire_dumps.py"),
                        "--output-dir", str(output_dir),
                        "--source", "sample",
                    ],
                    check=True,
                    cwd=str(ROOT),
                )
            if not input_path.exists():
                raise SystemExit(f"No text corpus at {input_path}. Run with --acquire first.")

    extract_cmd = [
        sys.executable, "-m", "src.ingestion.extraction_pipeline",
        "--input-path", str(input_path),
    ]
    if args.live:
        extract_cmd.append("--live")
    if args.no_clusters:
        extract_cmd.append("--no-clusters")
    subprocess.run(extract_cmd, check=True, cwd=str(ROOT))


if __name__ == "__main__":
    main()
