# Development Roadmap (Step 8)

This document describes the **five-stage development roadmap** for GOAT-TS: what each stage covers and how to run or test it. The system **currently implements** these stages; for **what the system does and how to use it day-to-day**, see [README.md](README.md). Implement stages sequentially; after each, run tests, update README and examples, and commit with the suggested message. **No silent fallbacks** — if a dependency (e.g. APScheduler, Spark, Redis) is required, document it and fail or skip explicitly.

---

## Stage 1: Core loop

**Scope:** Seeds → spread activation → memory_tick → optional forces; CLI args, logs, Graphviz export.

**What’s implemented:**
- **`src/agi_loop/demo_loop.py`** — run_demo(): seeds, activate_and_propagate, memory_tick, optional _apply_gravity_step; CLI for --seed-ids, --seed-labels, --ticks, --decay-rate, --enable-forces, --export-dot, --verbose, --dry-run.
- Logging and optional Graphviz export on final tick.

**Run:**
```bash
python -m src.agi_loop.demo_loop --dry-run --seed-labels concept --ticks 5 --export-dot demo_out.dot
```

**Tests:** **`tests/milestone_roadmap_stage1.py`** (core loop dry-run).

**Commit message:** `Stage 1: Core loop (seeds → spread → memory_tick → forces; CLI, logs, Graphviz)`

---

## Stage 2: Online learning, reflection

**Scope:** Online ingestion, stream/web search, low-coherence trigger; reflection (tension → meta-waves, hypothesis nodes).

**What’s implemented:**
- **Online learning:** `src/ingestion/ingestion_online.py` (stream_ingest, web_search, low-coherence trigger); `src/graph/query_handler.py` (decompose_query, search_and_fetch, handle_query, TF-IDF relevance).
- **Reflection:** `src/reasoning/reflection.py` (run_reflection: tension → meta-waves, hypothesis nodes); `src/reasoning/self_reflection.py` (long-term: wave gaps → goal nodes).

**Run:**
- Reasoning with reflection: **`python scripts/run_reasoning_demo.py --query "..." --live`**
- AGI loop with self-reflection: **`python -m src.agi_loop.demo_loop --dry-run --enable-self-reflection --ticks 10`**

**Tests:** **`tests/milestone_roadmap_stage2.py`** (reflection and/or online ingestion paths).

**Commit message:** `Stage 2: Online learning, reflection (stream ingest, query_handler, reflection, self_reflection)`

---

## Stage 3: Distributed (Spark/Redis/K8s), GPU opt

**Scope:** Spark ETL and batch ingestion; Redis cache for reasoning; Kubernetes deployment scaffolding; GPU option for PyTorch/FAISS.

**What’s implemented:**
- **Spark:** `scripts/run_spark_etl.py`, `scripts/run_batch_ingestion.py`; Docker service `spark` in `docker/docker-compose.yml`. Requires Java (JAVA_HOME).
- **Redis:** `src/reasoning/cache.py` (CacheAdapter); config in `configs/reasoning.yaml` (cache_enabled). Docker service `redis` in compose.
- **Kubernetes:** `infra/terraform/`, optional Deployment/Service in `infra/k8s/`.
- **GPU:** Optional CUDA for PyTorch; FAISS GPU via env `GOAT_USE_GPU=1` or config. Document in README; no silent CPU fallback in strict mode.

**Run:**
- Spark ETL: **`python scripts/run_spark_etl.py`** (with JAVA_HOME set).
- Redis: enable in `configs/reasoning.yaml` and start with **`docker compose -f docker/docker-compose.yml up -d`**.

**Tests:** Expand milestone tests to optionally exercise cache (if Redis URL set); document Spark/Java requirement.

**Commit message:** `Stage 3: Distributed (Spark/Redis/K8s), GPU opt scaffolding`

---

## Stage 4: Advanced (pred, sim, curiosity), hybrid LLM, Streamlit

**Scope:** Prediction, simulation sandbox, curiosity; hybrid LLM in reasoning; Streamlit visualization and full GUI.

**What’s implemented:**
- **Advanced:** `src/reasoning/prediction.py`, `src/reasoning/simulation_sandbox.py`, `src/reasoning/curiosity.py`. Wired in demo_loop via --enable-goal-generator, --enable-curiosity, --enable-sandbox.
- **Hybrid LLM:** Reasoning loop uses LLM when configured (`configs/reasoning.yaml`, extraction); reflection can call LLM for merge prompts.
- **Streamlit:** **`scripts/streamlit_viz.py`** — short demo or graph stats; **`scripts/goat_ts_gui.py`** — full GUI (Setup Wizard, Config, Ingestion, Simulation, Reasoning, Monitoring, Export & API).

**Run:**
- Demo with curiosity/goals: **`python -m src.agi_loop.demo_loop --dry-run --enable-goal-generator --enable-curiosity --ticks 5`**
- Full GUI: **`python -m streamlit run scripts/goat_ts_gui.py`**
- Lightweight viz: **`python -m streamlit run scripts/streamlit_viz.py`**

**Tests:** Existing Step 6/7 tests; optional test that Streamlit app loads.

**Commit message:** `Stage 4: Advanced (pred, sim, curiosity), hybrid LLM, Streamlit viz`

---

## Stage 5: Benchmarks, API, docs

**Scope:** Benchmark tests (consistency, reasoning PuLP, efficiency, interpretability); HTTP API for demo/reasoning; README and examples.

**What’s implemented:**
- **Benchmarks:** **`tests/test_benchmarks_step6.py`** (path trace, PuLP, timings, Graphviz export).
- **API:** **`scripts/serve_api.py`** (FastAPI) — POST /run_demo, POST /reasoning, GET /health.
- **Docs:** README, README_ARCHITECTURE, CODEBASE, CONTRIBUTING, PLATFORM, ROADMAP, examples/README, CHANGELOG.

**Run:**
- Benchmarks: **`python -m pytest tests/test_benchmarks_step6.py -v`**
- API: **`uvicorn scripts.serve_api:app --reload --host 0.0.0.0 --port 8000`**, then e.g. **`curl -X POST http://localhost:8000/run_demo -H "Content-Type: application/json" -d "{\"ticks\": 3, \"dry_run\": true}"`**

**Tests:** **`tests/test_serve_api.py`** (API endpoints).

**Commit message:** `Stage 5: Benchmarks, API, docs`

---

## After each stage

1. Run tests: **`python -m pytest -q`** (or **-v**).
2. Update README.md with any new commands, config, or examples.
3. Commit with the suggested message for that stage. If a dependency blocks (e.g. APScheduler, Java for Spark), **stop and notify**; do not add silent fallbacks.
