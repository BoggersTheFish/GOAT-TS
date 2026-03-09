from __future__ import annotations

import argparse
from pathlib import Path

from pyspark.sql import SparkSession


def build_spark_session(app_name: str = "ts-corpus-reader") -> SparkSession:
    return (
        SparkSession.builder.appName(app_name)
        .config("spark.sql.shuffle.partitions", "16")
        .getOrCreate()
    )


def read_text_corpus(input_path: str) -> "DataFrame":
    spark = build_spark_session()
    return spark.read.text(input_path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Read corpus chunks into Spark.")
    parser.add_argument("--input-path", required=True, help="Path to chunked text files.")
    parser.add_argument(
        "--output-path",
        required=True,
        help="Path to write intermediate parquet output.",
    )
    args = parser.parse_args()

    output_path = Path(args.output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    df = read_text_corpus(args.input_path).repartition(16)
    df.write.mode("overwrite").parquet(str(output_path))


if __name__ == "__main__":
    main()
