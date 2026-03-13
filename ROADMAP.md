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

## Stage 6: Usability enhancements

**Scope:** Simplify setup (no-Docker defaults); user-friendly wizards/onboarding; lightweight modes without Spark/Java; CLI presets; one-click demos.

**What's implemented:**
- **Presets:** `configs/presets.yaml` (quick-demo, full-demo, lightweight). Use **`--preset <name>`** with `demo_loop` or `one_click_demo`.
- **One-click demo:** **`scripts/one_click_demo.py`** — runs cognition loop + optional `--reasoning-query` in one go; no Docker when using default preset.
- **GUI:** Lightweight mode checkbox in Setup Wizard; when on, all features use in-memory fallback (dry-run).
- **Fallback:** All features work in dry-run; Spark/Java optional.

**Run:**
- **`python scripts/one_click_demo.py --preset quick-demo`**
- **`python -m src.agi_loop.demo_loop --preset lightweight --dry-run --ticks 3`**

**Tests:** **`tests/test_stage6_usability.py`** (one_click_demo, preset quick-demo, presets config).

---

## Stage 7: Real-world integrations

**Scope:** Connectors (web APIs, RSS); example apps (Q&A bot, knowledge explorer); reasoning output for apps (JSON).

**What's implemented:**
- **Connectors:** **`src/ingestion/connectors.py`** — `fetch_urls`, `rss_feed_to_chunks`; **`configs/ingestion_sources.yaml`** for RSS/URL lists.
- **API:** **`POST /reasoning`** accepts **`output_format: "app"`** for full JSON (activated_nodes, graph_context, hypotheses).
- **Example apps:** **`scripts/app_qa_bot.py`** (Q&A loop, single or interactive); **`scripts/app_knowledge_explorer.py`** (query → subgraph JSON).

**Run:**
- **`python scripts/app_qa_bot.py --query "What is a knowledge graph?"`**
- **`python scripts/app_knowledge_explorer.py "gravity" --output out.json`**

**Tests:** **`tests/test_stage7_integrations.py`** (connectors, knowledge explorer, Q&A bot).

---

## Stage 8: Optimization and scaling

**Scope:** Full distributed (K8s HPA); performance tuning; efficiency metrics; GPU benchmark.

**What's implemented:**
- **K8s:** **`infra/k8s/hpa.yaml`** — HorizontalPodAutoscaler for goat-app (CPU/memory targets).
- **Monitoring:** **`src/monitoring/metrics.py`** — `ticks_per_second`, `graph_size_nodes` gauges.
- **GPU benchmark:** **`scripts/run_gpu_benchmark.py`** — short cognition loop with forces; set `GOAT_USE_GPU=1` or config for CUDA.

**Run:**
- **`python scripts/run_gpu_benchmark.py`** (CPU fallback if no CUDA)
- **`kubectl apply -f infra/k8s/hpa.yaml -n <namespace>`** (after deployment)

**Tests:** **`tests/test_stage8_scale.py`** (medium graph demo, gpu benchmark script, efficiency metrics).

---

## Stage 9: Community and ecosystem

**Scope:** Plugin system; extensions gallery; CI already in place (see .github/workflows/ci.yml).

**What's implemented:**
- **Plugins:** **`src/plugins/__init__.py`** — `load_plugin(name)`, `load_all_plugins(config_root)`; **`configs/plugins.yaml`** (`plugins.enabled`); **`src/plugins/example_hook.py`** (PLUGIN_HOOKS).
- **Docs:** **`docs/extensions.md`** — extensions gallery (connectors, apps, presets, API output_format).

**Run:**
- Enable a plugin by adding its name to `configs/plugins.yaml` under `plugins.enabled`. Hook call sites can be added in reasoning/API later.

**Tests:** **`tests/test_stage9_plugins.py`** (load example_hook, load_all_plugins, plugins config).

---

## Stage 10: Advanced evolution

**Scope:** Meta-reasoning (curiosity over repo); self-assessment demos.

**What's implemented:**
- **Meta-reasoning:** **`src/reasoning/meta_reasoning.py`** — `repo_curiosity_scan`, `roadmap_to_hypotheses`, `run_meta_reasoning` (scan repo + ROADMAP → hypotheses).
- **Self-assessment:** **`scripts/self_assessment_demo.py`** — runs benchmarks, writes **`examples/self_assessment_report.md`**.

**Run:**
- **`python -c "from src.reasoning.meta_reasoning import run_meta_reasoning; from pathlib import Path; print(run_meta_reasoning(Path('.')))"`**
- **`python scripts/self_assessment_demo.py`**

**Tests:** **`tests/test_stage10_meta.py`** (repo_curiosity_scan, roadmap_to_hypotheses, run_meta_reasoning, self_assessment_demo).

---

## After each stage

1. Run tests: **`python -m pytest -q`** (or **-v**).
2. Update README.md with any new commands, config, or examples.
3. Commit with the suggested message for that stage. If a dependency blocks (e.g. APScheduler, Java for Spark), **stop and notify**; do not add silent fallbacks.
