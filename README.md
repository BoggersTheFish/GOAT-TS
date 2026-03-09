# GOAT-TS

**GOAT-TS** (Thinking System) is a local-first scaffold for a knowledge-graph–driven cognition architecture: ingest text into a graph, run spreading activation and memory dynamics, then reason over tension and hypotheses. It validates the design on a single machine while keeping boundaries for scaling to Spark, Redis, and Kubernetes.

**Author:** [Ben Michalek](https://github.com/BoggersTheFish) (BoggersTheFish)

[![License](https://img.shields.io/badge/License-Open%20Source-blue.svg)](LICENSE)  
*Python 3.11+ · NebulaGraph · PyTorch · LangChain*

---

## Table of contents

- [Features](#features)
- [Documentation](#documentation)
- [Quick start](#quick-start)
- [Cognition loop & API](#cognition-loop--api)
- [Development roadmap](#development-roadmap)
- [Repository layout](#repository-layout)
- [Configuration & environment](#configuration--environment)
- [Ingestion & reasoning](#ingestion--reasoning)
- [Thinking Wave graph](#thinking-wave-cognition-graph)
- [Portability](#portability)
- [License](#license)

---

## Features

- **Graph-backed cognition:** NebulaGraph storage with in-memory dry-run; concept nodes, waves (cognitive episodes), and `relates` / `in_wave` edges.
- **Spreading activation & memory:** ACT-R style propagation, decay, and state transitions (ACTIVE → DORMANT → DEEP) with optional gravity simulation.
- **Reasoning loop:** Query → subgraph retrieval → tension computation → hypothesis generation; optional Redis cache and LLM integration.
- **Online learning & reflection:** Stream ingestion, web search, low-coherence triggers; reflection (tension → meta-waves, hypothesis nodes); long-term self-reflection (wave gaps → goal nodes).
- **Advanced capabilities:** Goal generation from tension, curiosity-driven exploration, internal simulation sandbox, knowledge compression (PyG → FAISS archive).
- **API & UI:** FastAPI server (`/run_demo`, `/reasoning`, `/health`); Streamlit visualization; optional Tk installer/dashboard (`goat_ui.py`).
- **Cross-platform:** Windows, macOS, Linux — same commands from repo root; see [PLATFORM.md](PLATFORM.md).

---

## Documentation

| Document | Description |
|----------|-------------|
| [README.md](README.md) | This file — overview, quick start, usage. |
| [README_ARCHITECTURE.md](README_ARCHITECTURE.md) | Technical architecture and compliance (Steps 1–7). |
| [ROADMAP.md](ROADMAP.md) | Five-stage development roadmap and commit guidance. |
| [CODEBASE.md](CODEBASE.md) | Codebase reference: modules, data models, scripts. |
| [CONTRIBUTING.md](CONTRIBUTING.md) | How to contribute, test, and open PRs. |
| [PLATFORM.md](PLATFORM.md) | Portability and per-OS notes. |
| [examples/README.md](examples/README.md) | Sample inputs, export shape, API request examples. |
| [CHANGELOG.md](CHANGELOG.md) | Documentation and feature change summary. |

---

## Quick start

Run all commands from the **repository root**. Use `python -m pytest` and `python scripts/...` (or `python -m src....`) so the same invocations work on Windows, macOS, and Linux.

### 1. Virtual environment and dependencies

**Windows (PowerShell):**
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

**macOS / Linux:**
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Sanity check (no Docker)

```bash
python scripts/apply_schema.py --dry-run
python -m pytest tests/test_placeholder.py -v
```

### 3. Optional: start infrastructure (NebulaGraph, Redis, Spark)

```bash
docker compose -f docker/docker-compose.yml up -d
```

Wait until services are up (`docker compose -f docker/docker-compose.yml ps`). Then:

```bash
python scripts/apply_schema.py --live
python scripts/generate_sample_100k.py --node-count 1000 --edge-count 2500 --live
```

### 4. Run tests

```bash
python -m pytest -q
```

---

## Cognition loop & API

### Cognition loop (CLI)

Run the AGI cognition loop (seeds → spreading activation → memory tick → optional gravity):

```bash
python -m src.agi_loop.demo_loop --dry-run --seed-labels concept --ticks 10 --export-dot demo_out.dot
```

With forces and optional capabilities (self-reflection, curiosity, goal generator):

```bash
python -m src.agi_loop.demo_loop --dry-run --seed-labels concept --ticks 10 --enable-forces --enable-goal-generator --enable-curiosity
```

### HTTP API

Start the API server (from repo root):

```bash
uvicorn scripts.serve_api:app --reload --host 0.0.0.0 --port 8000
```

| Endpoint | Description |
|----------|-------------|
| `POST /run_demo` | Run cognition demo. Body: `{"ticks": 5, "dry_run": true, "seed_labels": "concept"}`. |
| `POST /reasoning` | Run reasoning loop. Body: `{"query": "your query", "live": false}`. |
| `GET /health` | Health check. |

Example:

```bash
curl -X POST http://localhost:8000/run_demo -H "Content-Type: application/json" -d "{\"ticks\": 3, \"dry_run\": true}"
```

### Streamlit visualization

```bash
streamlit run scripts/streamlit_viz.py
```

Run a short cognition demo (dry-run) or view graph stats from the sidebar.

### Reasoning demo (script)

```bash
python scripts/run_reasoning_demo.py --query "Wikipedia supports free knowledge and Wikidata supports structured facts." --live
```

Omit `--live` for dry-run graph context.

---

## Development roadmap

The project follows a **five-stage roadmap**; see [ROADMAP.md](ROADMAP.md) for full detail and suggested commit messages.

| Stage | Scope | Quick test |
|-------|--------|------------|
| **1** | Core loop (seeds → spread → memory_tick → forces; CLI, Graphviz) | `python -m src.agi_loop.demo_loop --dry-run --ticks 5` |
| **2** | Online learning, reflection | `python -m pytest tests/milestone_roadmap_stage2.py -v` |
| **3** | Distributed (Spark/Redis/K8s), GPU opt | Docker Compose; `infra/k8s/deployment.yaml`; `configs/simulation.yaml` (`use_gpu`) |
| **4** | Advanced (pred, sim, curiosity), hybrid LLM, Streamlit | `streamlit run scripts/streamlit_viz.py` |
| **5** | Benchmarks, API, docs | `python -m pytest tests/test_benchmarks_step6.py tests/test_serve_api.py -v` |

---

## Repository layout

```text
GOAT/
├── configs/          # graph.yaml, reasoning.yaml, simulation.yaml
├── docker/           # Docker Compose (NebulaGraph, Redis, Spark)
├── examples/         # Sample input, export shape, API request examples
├── infra/            # Terraform, Ansible, K8s (deployment scaffolding)
├── scripts/          # Entry points: schema, ingestion, demos, export, API, Streamlit
├── src/               # Core packages
│   ├── agi_loop/     # Cognition demo loop (demo_loop.py)
│   ├── graph/        # Client, models, schema, cognition, vector index, compression
│   ├── ingestion/    # Extraction pipeline, LLM extract, online ingest
│   ├── reasoning/    # Loop, tension, reflection, goal generator, curiosity, sandbox
│   ├── simulation/    # Gravity, loop
│   ├── physics/      # Forces, layout
│   └── monitoring/   # Metrics (Prometheus)
├── tests/            # Pytest suite (milestones, benchmarks, API, graph, reasoning)
├── requirements.txt
├── pytest.ini
└── README.md
```

---

## Configuration & environment

- **NebulaGraph:** Default `root` / `nebula`, host `127.0.0.1`, port `9669`. Configure in `configs/graph.yaml` or override via a **`.env`** file in the repo root (see [.env.example](.env.example)): `NEBULA_HOST`, `NEBULA_PORT`, `NEBULA_USERNAME`, `NEBULA_PASSWORD`. The client loads these with `python-dotenv`.
- **Scripts:** Use **`--live`** to talk to the real graph; without it, scripts use dry-run (in-memory). Prefer **`--dry-run`** first when available.
- **GPU:** Optional CUDA/FAISS-GPU via `configs/simulation.yaml` (`use_gpu`) or env `GOAT_USE_GPU=1`; see [ROADMAP.md](ROADMAP.md) Stage 3.

---

## Ingestion & reasoning

### Verification and debug (after ingestion)

- **List concepts in a wave:** `python scripts/query_wave.py --list --live` then `python scripts/query_wave.py --wave-id <id> --live`
- **Graph stats:** `python scripts/dump_graph_stats.py --live`
- **Export subgraph (JSON + optional PNG):** `python scripts/export_subgraph.py --concept "Concept 1" --live --output out.json --plot out.png`
- **Gravity demo (no DB write):** `python scripts/run_gravity_demo.py --live --iterations 100 --output positions.json --plot layout.png`

### Dump acquisition, Spark ETL, batch ingestion

1. **Acquire:** `scripts/acquire_dumps.py` — `--source sample | wikipedia-api | wikipedia-sample`; writes to `data/raw/` (e.g. `wikipedia/abstracts.txt`).
2. **Spark ETL:** `scripts/run_spark_etl.py` — reads text, writes Parquet with `value` column. Requires Java (`JAVA_HOME`).
3. **Extraction:** `python -m src.ingestion.extraction_pipeline --input-path <path> [--live]` or combined: `scripts/run_batch_ingestion.py --acquire [--spark-etl] [--live]`.

### Hybrid LLM

Reasoning and reflection can use an LLM when configured: set `configs/reasoning.yaml` (e.g. `require_llm`, cache, node_limit). Extraction uses `TripleExtractor`; reflection can extend prompts via LLM. See `src/reasoning/reflection.py` and `src/ingestion/llm_extract.py`.

---

## Thinking Wave cognition graph

The graph stores a **cognition layer** alongside concept and topic nodes:

- **Wave** vertices = one cognitive episode (ingestion chunk or reasoning pass). Properties: `label`, `source` (`ingestion` | `reasoning`), `intensity`, `coherence`, `tension`, `source_chunk_id`.
- **in_wave** edges link concept nodes to waves (provenance: “this concept appeared in this episode”).
- **relates** edges = concept-to-concept (and concept–cluster). Simulation runs on concept/topic nodes and `relates` only.

**Schema:** `src/graph/schema/create_schema.ngql`. Apply with `python scripts/apply_schema.py --live` after creating the space.

---

## Portability

- **Paths:** Scripts use `pathlib.Path` and `ROOT = Path(__file__).resolve().parents[1]`; paths are built as `ROOT / "scripts" / "file.py"` so separators are correct on all OSes.
- **Subprocess:** Commands use `subprocess.run([sys.executable, ...], cwd=str(ROOT))` with list arguments (no `shell=True`).
- **PowerShell:** Use `;` instead of `&&` to chain commands; README uses one command per block for copy-paste.

See [PLATFORM.md](PLATFORM.md) for details and how to verify on your system.

---

## License

This project is open source. See [LICENSE](LICENSE) in the repository root for terms.
