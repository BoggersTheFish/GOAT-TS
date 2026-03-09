# GOAT TS Architecture

**Author:** Ben Michalek ([BoggersTheFish](https://github.com/BoggersTheFish))

This repository implements a local-first scaffold for the Thinking System (TS) architecture described in the plan. It is organized to validate the architecture on a single machine first, while keeping the module boundaries needed for later scaling to Spark, GPUs, Redis, and Kubernetes.

## Stack

- Python 3.11+
- NebulaGraph for graph storage
- Spark for ETL and batch processing
- Hugging Face / LangChain for semantic extraction
- PyTorch and NumPy for simulation math
- Prometheus and Grafana for monitoring

## Repository Layout

```text
GOAT/
├── docker/
├── infra/
├── src/
├── configs/
├── scripts/
├── tests/
├── requirements.txt
└── README.md
```

## Quick Start

1. Create a virtual environment and install dependencies:

   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```

2. Start local infrastructure:

   ```powershell
   .\scripts\start-local.ps1
   ```

3. Apply the graph schema:

   ```powershell
   python .\scripts\apply_schema.py --live
   ```

4. Generate a local sample graph:

   ```powershell
   python .\scripts\generate_sample_100k.py --node-count 100000 --edge-count 250000 --live
   ```

5. Run smoke tests:

   ```powershell
   pytest -q
   ```

## Phase Milestones

- Phase 1: local NebulaGraph, schema, graph client, extraction pipeline, and 100K-node loader
- Phase 2: dump acquisition, Spark ETL, and batch extraction/insertion (see below)
- Phase 3: gravity simulation, mass updates, and clustering hooks
- Phase 4: reasoning loop, contradiction detection, caching, and hypotheses
- Phase 5: monitoring, Terraform, Ansible, and deployment scaffolding

## Phase 2: Dump Acquisition, Spark ETL, Batch Ingestion

1. **Dump acquisition** – `scripts/acquire_dumps.py` downloads or generates corpus text:
   - `--source sample`: write built-in sentences to `data/raw/wikipedia/abstracts.txt`
   - `--source wikipedia-api`: fetch article summaries via Wikipedia REST API
   - `--source wikipedia-sample`: download and optionally parse an XML dump
   Use `--output-dir`, `--max-docs`, and `--parse` as needed.

2. **Spark ETL** – `scripts/run_spark_etl.py` reads text (one chunk per line) and writes parquet with a `value` column for the extraction pipeline. Default input: `data/raw/wikipedia/abstracts.txt`; default output: `data/processed/corpus.parquet`. Requires Java (`JAVA_HOME` set).

3. **Batch extraction/insertion** – The extraction pipeline accepts either a `.txt` file or parquet (file or directory with a `value` column). Run:
   - `python -m src.ingestion.extraction_pipeline --input-path <path> [--live]`
   Or use the combined script: `scripts/run_batch_ingestion.py --acquire [--spark-etl] [--live]` to run acquire, optional Spark ETL, and extraction in one go.

## Thinking Wave Cognition Graph

The graph stores a **cognition layer** alongside concept and topic nodes:

- **Wave** vertices represent one cognitive episode (e.g. one ingestion chunk or reasoning pass). Each has `label`, `source` (`ingestion` | `reasoning`), optional metrics (`intensity`, `coherence`, `tension`), and `source_chunk_id` for provenance.
- **in_wave** edges link concept nodes to waves: each concept that appears in a chunk is connected to that chunk’s wave, so retrieval can use wave-scoped context.

The extraction pipeline creates one wave per chunk (when using clusters), inserts wave vertices and `in_wave` edges into NebulaGraph, and the reasoning loop can expand context by including concepts from waves whose label matches the query. Simulation runs only on concept/topic nodes and `relates` edges; wave nodes are excluded.

**Schema:** `src/graph/schema/create_schema.ngql` defines the `wave` tag and `in_wave` edge. Apply with `python scripts/apply_schema.py --live` after creating the space.

**Loading:** Running the extraction pipeline (e.g. `python -m src.ingestion.extraction_pipeline --input-path data/raw/wikipedia/abstracts.txt --live`) inserts nodes, waves, and both `relates` and `in_wave` edges. Dry-run is supported for tests.

## License

This project is open source. See [LICENSE](LICENSE) in the repository root for terms.

## Notes

- The code includes dry-run and fallback logic so the repository can be exercised without a live graph database or GPU.
- Scale targets from the plan are represented as configuration and workload scripts; full production execution still requires cloud infrastructure and significant runtime resources.
- The `--live` flags on scripts switch from the default dry-run mode to real NebulaGraph execution.
