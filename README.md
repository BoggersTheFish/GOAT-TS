# GOAT-TS

**GOAT-TS** (Thinking System) is a **knowledge-graph–driven cognition scaffold**: you ingest text into a graph, run spreading activation and memory dynamics over it, then reason over tension and hypotheses. It is designed to run locally first (single machine) with clear paths to scale out (Spark, Redis, Kubernetes).

**Author:** [Ben Michalek](https://github.com/BoggersTheFish) (BoggersTheFish)

*Python 3.11+ · NebulaGraph · PyTorch · LangChain · Streamlit*

---

## What this system does

- **Stores knowledge in a graph.** Text is turned into **concepts** (nodes) and **relationships** (edges). Each ingestion chunk or reasoning pass is recorded as a **wave** (cognitive episode), so you can see which concepts came from which source.
- **Runs a cognition loop.** You seed the graph (by concept labels or node IDs), then the system spreads activation (ACT-R style), applies memory decay and state transitions (ACTIVE → DORMANT → DEEP), and optionally runs a gravity-style simulation to update positions and masses. That loop is the core “thinking” step.
- **Reasons over the graph.** You ask a query; the system retrieves a relevant subgraph, computes “tension” (mismatch between where nodes are and where they “should” be), and produces hypotheses (e.g. “What explains the conflict between X and Y?”). Results can be cached in Redis.
- **Supports ingestion and simulation.** You can acquire text (sample, Wikipedia API, or dumps), run Spark ETL to Parquet, extract triples (regex or LLM), merge similar concepts (FAISS), and load everything into NebulaGraph. Simulation reads from the graph, runs one physics step (forces, domains), and writes updated masses and cluster IDs back.

So: **ingest → graph → cognition loop (spread + memory + optional gravity) → reasoning (query → subgraph → tension → hypotheses).** All of this can run in **dry-run** (in-memory, no Docker) or **live** (NebulaGraph, Redis, Spark via Docker).

---

## Why it’s useful

- **Single place to try the pipeline.** One repo gives you acquisition, ETL, extraction, graph schema, activation, memory, reasoning, and simulation. You can validate the design and extend it without switching projects.
- **Local-first.** You can develop and test with `--dry-run` and no Docker; when ready, start Docker and use `--live` for real storage and caching.
- **Structured cognition model.** Waves and in_wave edges give you provenance (“this concept appeared in this chunk”); tension and hypotheses make reasoning interpretable; memory states (ACTIVE/DORMANT/DEEP) make decay and consolidation explicit.
- **Ready for extension.** The roadmap (core loop → online learning/reflection → distributed/GPU → advanced features → benchmarks/API/docs) is implemented in stages; see [ROADMAP.md](ROADMAP.md) and [README_ARCHITECTURE.md](README_ARCHITECTURE.md).

---

## How to use it

Run all commands from the **repository root**. Use `python -m streamlit run ...`, `python -m pytest`, and `python scripts/...` so the same invocations work on Windows, macOS, and Linux (see [PLATFORM.md](PLATFORM.md)).

### 1. Dependencies and GUI (recommended start)

Create a virtual environment and install dependencies:

**Windows (PowerShell):**
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

**macOS / Linux:**
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Start the **Streamlit GUI** (setup, config, ingestion, simulation, reasoning, monitoring, export, API):

```bash
python -m streamlit run scripts/goat_ts_gui.py
```

Open the URL shown (e.g. `http://localhost:8501`). In the sidebar go to **Setup Wizard**.

### 2. Setup Wizard (in the GUI)

1. Click **“Check system (verify all steps)”** to see what’s already done (dependencies, Docker, connection, schema). The sidebar shows **Deps**, **Docker**, **Connect**, **Schema** (✓ or —).
2. Complete any missing steps in order:
   - **Step 1 — Dependencies:** Install Python requirements (button runs `pip install -r requirements.txt`). Once verified or installed, the step is locked.
   - **Step 2 — Docker:** Start NebulaGraph, Redis, and Spark with “Start Docker,” then “Check Docker status.” When Docker is up, Start is locked.
   - **Step 3 — Connect:** Test connection to NebulaGraph (credentials in `configs/graph.yaml` and optional `.env`).
   - **Step 4 — Schema:** Apply schema (dry-run first, then “Apply schema (live)” once Docker is up). When the space exists and is applied, the live button is locked.
3. Time estimates per step use the last run duration when available; completed steps are locked so you don’t re-run them by mistake.

You can also run these steps from the terminal (see [PLATFORM.md](PLATFORM.md) and sections below).

### 3. After setup: what you can do

- **Config Editor** — Load, edit, and save `configs/graph.yaml`, `configs/reasoning.yaml`, `configs/simulation.yaml`.
- **Data Ingestion** — Acquire dumps (sample / wikipedia-api / wikipedia-sample), run Spark ETL, run the extraction pipeline (dry-run or `--live`).
- **Simulation & Physics** — Run one simulation step from the graph (optionally with live write-back), or run the gravity demo.
- **Reasoning Loop** — Run the reasoning demo with a query (dry-run or live).
- **Monitoring & Debug** — Dump graph stats, list waves, export subgraph (JSON/PNG). Use **Export & API** to start the HTTP API server.
- **Debug log** — Open `http://localhost:8501/?page=debug` to see subprocess output (e.g. pip, Docker, schema).

### 4. Cognition loop (CLI)

Run the AGI-style cognition loop (seeds → spreading activation → memory tick → optional gravity):

```bash
python -m src.agi_loop.demo_loop --dry-run --seed-labels concept --ticks 10 --export-dot demo_out.dot
```

With forces and optional capabilities (self-reflection, curiosity, goal generator):

```bash
python -m src.agi_loop.demo_loop --dry-run --seed-labels concept --ticks 10 --enable-forces --enable-goal-generator --enable-curiosity
```

Use `--dry-run` for in-memory (no Nebula); omit it and ensure Docker + schema are up for live runs.

### 5. HTTP API

Start the API server from repo root:

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

### 6. Optional: Streamlit visualization (lightweight)

A simpler Streamlit app for running a short demo or viewing graph stats:

```bash
python -m streamlit run scripts/streamlit_viz.py
```

---

## Documentation index

| Document | What it’s for |
|----------|----------------|
| [README.md](README.md) | This file — what the system does, why it’s useful, how to use it. |
| [README_ARCHITECTURE.md](README_ARCHITECTURE.md) | Technical architecture: ingestion, graph, simulation, reasoning, compliance (Steps 1–7), demo loop, benchmarks. |
| [ROADMAP.md](ROADMAP.md) | Five-stage development roadmap and how to run each stage. |
| [CODEBASE.md](CODEBASE.md) | Codebase reference: modules, data models, scripts, configs. |
| [CONTRIBUTING.md](CONTRIBUTING.md) | How to contribute, run tests, and open PRs. |
| [PLATFORM.md](PLATFORM.md) | Portability (Windows, macOS, Linux) and how to verify. |
| [examples/README.md](examples/README.md) | Sample input, export shape, API request examples. |
| [CHANGELOG.md](CHANGELOG.md) | Summary of documentation and feature changes. |

---

## Repository layout

```text
GOAT/
├── configs/          # graph.yaml, reasoning.yaml, simulation.yaml (and optional llm.yaml)
├── docker/           # Docker Compose (NebulaGraph, Redis, Spark)
├── examples/         # Sample input, export shape, API examples
├── infra/            # Terraform, Ansible, K8s (deployment scaffolding)
├── scripts/          # Entry points: schema, ingestion, demos, export, API, Streamlit GUI
├── src/              # Core packages
│   ├── agi_loop/     # Cognition demo loop (demo_loop.py)
│   ├── graph/        # Client, models, schema, vector index, compression
│   ├── ingestion/    # Extraction pipeline, LLM extract, online ingest
│   ├── reasoning/    # Loop, tension, reflection, goal generator, curiosity, cache
│   ├── simulation/   # Gravity, loop
│   ├── physics/      # Forces, layout
│   └── monitoring/   # Metrics (Prometheus)
├── tests/            # Pytest suite (milestones, benchmarks, API, graph, reasoning)
├── requirements.txt
├── pytest.ini
└── README.md
```

---

## Configuration and environment

- **NebulaGraph:** Default `root` / `nebula`, host `127.0.0.1`, port `9669`. Set in `configs/graph.yaml` or override with a **`.env`** in the repo root: `NEBULA_HOST`, `NEBULA_PORT`, `NEBULA_USERNAME`, `NEBULA_PASSWORD` (see `.env.example`).
- **Scripts:** Use **`--live`** to talk to the real graph and Redis; without it, scripts use dry-run (in-memory). Prefer **`--dry-run`** first when available.
- **GPU:** Optional CUDA/FAISS-GPU via `configs/simulation.yaml` (`use_gpu`) or env `GOAT_USE_GPU=1`; see [ROADMAP.md](ROADMAP.md).

---

## Ingestion and reasoning (terminal)

- **Acquire text:** `python scripts/acquire_dumps.py --source sample` (or `wikipedia-api`, `wikipedia-sample`); output under `data/raw/`.
- **Spark ETL:** `python scripts/run_spark_etl.py` — reads text, writes Parquet (`value` column). Requires Java (`JAVA_HOME`).
- **Extraction:** `python -m src.ingestion.extraction_pipeline --input-path <path> [--live]` or combined: `scripts/run_batch_ingestion.py --acquire [--spark-etl] [--live]`.
- **Reasoning demo:** `python scripts/run_reasoning_demo.py --query "your query" --live` (omit `--live` for dry-run).
- **Graph stats / export:** `python scripts/dump_graph_stats.py --live`; `python scripts/export_subgraph.py --concept "X" --live --output out.json --plot out.png`.

---

## Thinking Wave graph (cognition layer)

The graph stores a **cognition layer** alongside concepts:

- **Nodes** = concepts (and topic/cluster nodes). Properties include `label`, `mass`, `activation`, `state` (ACTIVE/DORMANT/DEEP), `cluster_id`, `metadata`.
- **Waves** = one cognitive episode per ingestion chunk or reasoning pass. Properties: `label`, `source` (e.g. `ingestion` / `reasoning`), `intensity`, `coherence`, `tension`, `source_chunk_id`.
- **relates** = concept-to-concept (and concept–cluster) edges.
- **in_wave** = edges from concept nodes to waves (provenance: “this concept appeared in this episode”).

Schema is in `src/graph/schema/`; apply with `python scripts/apply_schema.py --live` after the space is created.

---

## Portability

Paths use `pathlib.Path`; subprocesses use list arguments and `cwd=ROOT`. On Windows use `;` instead of `&&` to chain commands. See [PLATFORM.md](PLATFORM.md) for details and verification steps.

---

## License

This project is open source. See [LICENSE](LICENSE) in the repository root for terms.
