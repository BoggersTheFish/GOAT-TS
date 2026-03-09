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

Run all commands from the **repository root**. Use `python -m pytest` (and `python scripts/...`) so the same command works on Windows, macOS, and Linux.

### 1. Virtual environment and dependencies

**Windows (PowerShell):**
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

**macOS / Linux (bash):**
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Start local infrastructure (NebulaGraph, Redis, Spark)

**All platforms (Docker Compose V2):**
```bash
docker compose -f docker/docker-compose.yml up -d
```

**Windows only (alternative):** `.\scripts\start-local.ps1`  
**macOS / Linux only (alternative):** `bash scripts/start-local.sh` or `chmod +x scripts/start-local.sh && ./scripts/start-local.sh`

Wait until services are up: `docker compose -f docker/docker-compose.yml ps` should show graphd, storaged, metad, redis, spark as running.

### 3. Apply the graph schema

```bash
python scripts/apply_schema.py --dry-run
python scripts/apply_schema.py --live
```

(On Windows you can use `python .\scripts\apply_schema.py`; forward slashes in paths work in Python on all platforms.)

### Connection and auth

- **NebulaGraph** default is `root` / `nebula`, host `127.0.0.1`, port `9669`. Set in `configs/graph.yaml`. Change `username` / `password` there if your instance differs.
- Scripts use **`--live`** to talk to the real graph; without `--live` they use dry-run (no connection). Prefer **`--dry-run`** first when a script supports it.

### 4. Generate a local sample graph

```bash
python scripts/generate_sample_100k.py --node-count 1000 --edge-count 2500 --live
```

### 5. Run smoke tests

```bash
python -m pytest -q
```

At least one trivial test (`tests/test_placeholder.py`) and the milestone tests should pass. See `pytest.ini` for ignored modules.

## Why this works on your system (and others)

- **Paths:** All scripts use `pathlib.Path` and `ROOT = Path(__file__).resolve().parents[1]`. Paths are built with `ROOT / "scripts" / "file.py"` and passed as `str(...)` only when needed (e.g. subprocess, config). So path separators are correct on Windows (`\`) and Unix (`/`).
- **Subprocess:** Scripts call `subprocess.run([sys.executable, ...], cwd=str(ROOT))` with a **list** of arguments (no `shell=True`). The same Python and working directory are used on every OS.
- **Environment:** When spawning subprocesses, scripts set `PYTHONPATH=str(ROOT)` (or `cwd=ROOT`) so imports resolve the same way as in your terminal when you run from repo root.
- **Docker:** The compose file path is passed as a single argument; Docker Compose accepts both forward and backslash paths. The UI uses a normalized path for the compose file when starting services.
- **One command per line:** In PowerShell, `&&` is not valid; use `;` or run commands separately. The README uses one command per block so you can copy-paste safely on any shell.

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
- **Portability:** The same repo and commands are intended to work on Windows, macOS, and Linux. See [PLATFORM.md](PLATFORM.md) for how this is done and how to verify on your system.
