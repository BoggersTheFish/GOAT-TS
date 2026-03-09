# GOAT-TS Architecture Reference

This document describes the **technical architecture of the system we currently have**: ingestion, graph storage, simulation, reasoning, cognition loop, and how it aligns with the specified baseline (Steps 1–7). For **what the system does, how to use it, and why it’s useful**, see [README.md](README.md).

**Repository:** [github.com/BoggersTheFish/GOAT-TS](https://github.com/BoggersTheFish/GOAT-TS) (local path may be `GOAT`).

---

## 1. System overview

**Current flow:** Text is acquired or generated → (optionally) Spark ETL to Parquet → extraction pipeline turns chunks into triples, then into **nodes** (concepts + topic nodes), **waves** (one per chunk), and **relates** / **in_wave** edges. The graph is stored in NebulaGraph (or in-memory for dry-run). The **cognition loop** seeds the graph, runs spreading activation, memory decay/state transitions, and optionally gravity; the **reasoning loop** takes a query, retrieves a subgraph, computes tension, and produces hypotheses. Simulation can read from the graph, run one physics step (forces, domain detection), and write updated masses and cluster IDs back.

---

## 2. Ingestion pipeline

- **Acquisition:** `scripts/acquire_dumps.py` — downloads or generates corpus text (`--source sample | wikipedia-api | wikipedia-sample`), writes to `data/raw/` (e.g. `wikipedia/abstracts.txt`). `scripts/generate_sample_100k.py` generates synthetic nodes/edges for testing; can write to NebulaGraph with `--live`.
- **ETL:** `scripts/run_spark_etl.py` — reads text (e.g. one chunk per line), writes Parquet with a `value` column. Requires Java/Spark.
- **Extraction:** `src/ingestion/extraction_pipeline.py` — consumes `.txt` or Parquet (with `value` column). Uses regex and/or LLM (`src/ingestion/llm_extract.py`, `TripleExtractor`) to produce triples. Builds **waves**, **nodes** (concepts + cluster/topic nodes), **relates** and **in_wave** edges. Node IDs from `stable_node_id()` (UUIDv5). Writes to NebulaGraph when `--live`. Optional **global concept merging** (FAISS, `--global-merge`, `--merge-threshold`).
- **Support:** `scripts/run_batch_ingestion.py`, `scripts/run_ingestion_pipeline.py` chain acquire → [Spark] → extraction → load.

---

## 3. Graph storage (NebulaGraph)

- **Client:** `src/graph/client.py` — `NebulaGraphClient` reads `configs/graph.yaml` and `.env`. Dry-run uses `InMemoryGraphStore`; live connects to NebulaGraph (space `ts_graph`).
- **Schema:** `src/graph/schema/create_space.ngql` (space `ts_graph`, `vid_type = FIXED_STRING(64)`); `create_schema.ngql` — tag `node` (label, mass, activation, state, cluster_id, metadata), tag `wave` (label, source, intensity, coherence, tension, source_chunk_id), edges `relates` and `in_wave` with weight. Indexes on label, state, wave source. **No vector type in Nebula**; embeddings live in node metadata; FAISS is used as external vector backend.
- **Models:** `src/graph/models.py` — `Node`, `Edge`, `Wave`, `Triple`, `MemoryState` (ACTIVE/DORMANT/DEEP). Cognition ontology in `src/graph/cognition.py` (relates, in_wave, wave sources).

---

## 4. Physics and simulation

- **Forces:** `src/physics/forces.py` — attraction, repulsion, spring (NumPy); FAISS-based approximate neighbor pairs for large graphs.
- **Gravity:** `src/simulation/gravity.py` — `build_state`, `compute_forces`, `update_positions`; config from `configs/simulation.yaml`.
- **Simulation loop:** `src/simulation/loop.py` — `run_simulation_step`, `run_from_graph` (snapshot from Nebula, one physics step, domain detection via Louvain, optional persist). Writes back mass, activation, state, cluster_id when `--live`.

---

## 5. Reasoning

- **Loop:** `src/reasoning/loop.py` — Query → cache check → triple extraction on query → `retrieve_graph_context` (subgraph by keywords/clusters/waves) → tension computation → hypotheses (high-tension pairs) → cache set. Optional persistence of reasoning wave and in_wave edges when live.
- **Tension:** `src/reasoning/tension.py` — `compute_tension(positions, expected_distances)` → `TensionResult` (score, high_tension_pairs).
- **Cache:** `src/reasoning/cache.py` — `CacheAdapter` with Redis when `cache_enabled` in `configs/reasoning.yaml`; otherwise no-op.

---

## 6. Cognition loop (AGI demo)

**Current implementation:** `src/agi_loop/demo_loop.py` — `run_demo()`: load or build graph → each tick: (1) spread activation from seeds (ACT-R style, `activation.py`), (2) memory tick (decay + state transitions + DEEP promotion, `memory_manager.py`), (3) optional gravity step (`gravity.build_state` → forces → update positions), (4) optional self-reflection, goal generator, curiosity, sandbox, compression. Logs ACTIVE/DORMANT/DEEP counts, top activations; can export Graphviz `.dot`. CLI: `--dry-run`, `--seed-labels`, `--seed-ids`, `--ticks`, `--decay-rate`, `--enable-forces`, `--export-dot`, `--enable-self-reflection`, `--enable-goal-generator`, `--enable-curiosity`, etc.

**Run (in-memory):**
```bash
python -m src.agi_loop.demo_loop --dry-run --seed-labels concept --ticks 20
```

With Graphviz export:
```bash
python -m src.agi_loop.demo_loop --dry-run --seed-labels "concept,apple" --ticks 15 --export-dot out/demo.dot --verbose
```

---

## 7. Monitoring and deployment

- **Monitoring:** `src/monitoring/metrics.py` — Prometheus metrics stubs; optional Grafana dashboard JSON under `src/monitoring/grafana/`.
- **Deployment:** `docker/` — Docker Compose for NebulaGraph, Redis, Spark. `infra/` — Terraform, Ansible, K8s scaffolding (e.g. `infra/k8s/deployment.yaml`).

---

## 8. Implemented vs baseline (summary)

| Area | Implemented in current system |
|------|-------------------------------|
| Graph / nodes | Tags node/wave, edges relates/in_wave, mass/activation/state, indexes; FAISS vector backend; global concept merge (cluster_merge.py). |
| Persistent memory | NebulaGraph + InMemoryGraphStore; optional SQLite backup; `backup_snapshot` for versioning. |
| Activation / propagation | Spreading activation (activation.py), damped propagation; FAISS approx for large n. |
| Memory system | decay_activations, state transitions (ACTIVE→DORMANT→DEEP), promote_to_deep_after_ticks, memory_tick (memory_manager.py). |
| AGI loop | demo_loop: seeds → spread → memory_tick → optional gravity; Graphviz export. |
| Reasoning | retrieve_graph_context, tension, hypotheses; Redis cache; optional reasoning wave persistence. |
| Learning / feedback | Post-wave feedback; high-tension reweighting of edges (update_edges). |
| LLM / extraction | TripleExtractor (regex + optional Hugging Face); confidence filter; require_llm, min_confidence in pipeline. |
| Wave propagation | wave_propagation.py (decompose_input, propagate_wave, align/oppose by embedding). |
| Importance / GAT | importance_weighting.py (update_mass_from_activation, evolve_edges_with_gat). |
| Reflection / self-reflection | reflection.py (tension → meta-waves, hypothesis nodes); self_reflection.py (wave gaps → goal nodes). |
| Consolidation / abstraction | consolidation.py (merge, prune, state transitions, Redis tier, APScheduler); abstraction.py (Louvain, Leiden, hierarchical, super-nodes). |
| Prediction | prediction.py (forward_simulate, predictive_activation_error, free-energy, backprop_errors_to_edges). |
| Layout / forces | Fruchterman-Reingold, SOM (MiniSom) in forces.py. |
| Online learning / query | ingestion_online.py (stream_ingest, web_search, low-coherence trigger); query_handler.py (decompose_query, search_and_fetch, TF-IDF relevance). |
| Noise filter | noise_filter.py (low-confidence filter, tension outliers via IsolationForest). |
| Benchmarks (Step 6) | Consistency, reasoning (PuLP), efficiency, interpretability (Graphviz) in tests/test_benchmarks_step6.py. |
| Step 7 capabilities | Goal generator, curiosity, simulation sandbox, long-term self-reflection, knowledge compression (PyG → FAISS archive). |
| API / UI | serve_api.py (FastAPI: /run_demo, /reasoning, /health); goat_ts_gui.py (Streamlit: Setup Wizard, Config, Ingestion, Simulation, Reasoning, Monitoring, Export & API); streamlit_viz.py; optional goat_ui.py (Tk). |

---

## 9. Key scripts and configs

- **Scripts:** `apply_schema.py`, `acquire_dumps.py`, `generate_sample_100k.py`, `run_spark_etl.py`, `run_simulation.py`, `run_reasoning_demo.py`, `export_subgraph.py`, `dump_graph_stats.py`, `query_wave.py`, `run_gravity_demo.py`, `goat_ts_gui.py` (Streamlit full GUI), `streamlit_viz.py`, `serve_api.py`.
- **Configs:** `configs/graph.yaml` (Nebula, space, dry_run, batch_size), `configs/reasoning.yaml` (cache, Redis, node_limit, edge_limit), `configs/simulation.yaml` (gravity params, use_gpu). Optional `configs/llm.yaml` for extraction.
- **Dependencies:** nebula3-python, langchain, transformers, torch, numpy, networkx, matplotlib, pyyaml, python-dotenv, requests, tqdm, sentence-transformers, faiss-cpu; optional: pyarrow, pyspark, redis, prometheus-client, leidenalg, igraph, minisom, pulp, streamlit, torch-geometric, apscheduler.

---

## 10. Compliance tables (Steps 2–7)

Detailed compliance for Steps 2–5 (architectural fixes, major upgrades, suggested algorithms, learning) and Steps 6–7 (benchmarks, new capabilities) is preserved in the repository history. The sections above summarize what is **currently implemented**. For exact spec items and file references, see the full architecture doc in version control or the tables previously under §§10–15 (vector backend, global merge, propagation, memory, learning, LLM, SQLite/Redis, wave propagation, importance weighting, reflection, consolidation, abstraction, prediction, online learning, query handler, noise filter, benchmarks, self-reflection, sandbox, goal generator, curiosity, compression).

---

## 11. How to run a minimal cognition cycle

1. **Dry-run (no Docker):** `python -m src.agi_loop.demo_loop --dry-run --ticks 20`
2. **With Docker + schema:** Start Docker, `python scripts/apply_schema.py --live`, then e.g. `python scripts/generate_sample_100k.py --node-count 1000 --edge-count 2500 --live`, then run demo without `--dry-run` (or use Streamlit GUI Setup Wizard to do the same from the browser).

For more usage and setup, see [README.md](README.md).
