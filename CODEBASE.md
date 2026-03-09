# GOAT-TS Codebase Reference

This document is a **codebase reference** for GOAT-TS: where things live and what each part does. For **what the system does, how to use it, and how to get started**, see [README.md](README.md).

---

## 1. What the codebase is

GOAT-TS is a **local-first scaffold** for a knowledge-graph–driven “Thinking System.” The codebase provides:

1. **Ingestion** — Acquire text → (optionally) Spark ETL → extract triples → insert **nodes**, **waves**, and **edges** into the graph.
2. **Reasoning** — Given a query, retrieve a subgraph, compute tension, produce hypotheses; optional Redis cache and reasoning-wave persistence.
3. **Simulation** — Load a subgraph from the graph, run one gravity-style physics step (forces, domains), write updated masses/activations/cluster_id back when live.
4. **Cognition loop** — Seeds → spreading activation → memory tick → optional gravity and optional extras (self-reflection, curiosity, goal generator, compression).

Everything can run in **dry-run** (in-memory) or **live** (NebulaGraph, Redis, Spark via Docker).

---

## 2. Repository layout

```text
GOAT/
├── configs/           # graph.yaml, reasoning.yaml, simulation.yaml (optional llm.yaml)
├── docker/            # Docker Compose (NebulaGraph, Redis, Spark)
├── examples/         # Sample input, export shape, API examples
├── infra/             # Terraform, Ansible, K8s (deployment scaffolding)
├── scripts/           # Schema, ingestion, demos, export, API, Streamlit GUI
├── src/               # Core Python packages
│   ├── agi_loop/      # Cognition demo loop (demo_loop.py)
│   ├── graph/         # Client, models, schema, cognition, vector index, compression
│   ├── ingestion/     # Extraction pipeline, LLM extract, online ingest
│   ├── reasoning/     # Loop, tension, reflection, goal generator, curiosity, sandbox, cache
│   ├── simulation/    # Gravity, loop
│   ├── physics/       # Forces, layout
│   ├── monitoring/    # Metrics (Prometheus)
│   └── utils.py       # Config loading and helpers
├── tests/             # Pytest: milestones, benchmarks, API, graph, reasoning, physics
├── requirements.txt
├── pytest.ini
└── README.md
```

---

## 3. Core data models and graph ontology

### 3.1 Models (`src/graph/models.py`)

- **`Node`** — Concept or topic: node_id, label, mass, activation, state (ACTIVE/DORMANT/DEEP), cluster_id, embedding, position, velocity, metadata. Used across ingestion, reasoning, simulation.
- **`Edge`** — src_id, dst_id, relation (e.g. relates, in_wave), weight, metadata.
- **`Wave`** — One cognitive episode: wave_id, label, source (ingestion/reasoning), intensity, coherence, tension, source_chunk_id.
- **`Triple`** — subject, relation, object, confidence (from extraction).
- **`MemoryState`** — ACTIVE, DORMANT, DEEP.
- **`NodeType`** — KNOWLEDGE, QUESTION, HYPOTHESIS, etc. (in metadata).

### 3.2 Cognition ontology (`src/graph/cognition.py`)

- **relates** — Concept-to-concept (and concept–cluster) edges.
- **in_wave** — Edge from concept **node** to **wave** vertex (provenance).
- **WAVE_SOURCE_INGESTION** / **WAVE_SOURCE_REASONING** — Values for `Wave.source`.

---

## 4. Graph layer (`src/graph/`)

- **`client.py`** — `NebulaGraphClient` (config from graph.yaml + .env), `InMemoryGraphStore` for dry-run. insert_nodes/edges/waves, update_nodes, get_node, list_*, snapshot, snapshot_induced_by_edges.
- **`schema/`** — create_space.ngql, create_schema.ngql (tags node/wave, edges relates/in_wave). Applied by `scripts/apply_schema.py` (--live, optional --reset).
- **`vector_index.py`** — FAISS-backed EmbeddingVectorIndex (add, search_knn, search_by_threshold, find_similar_pairs, save/load). Embeddings in node metadata.
- **`cluster_merge.py`** — global_concept_merge (threshold, FAISS, union-find).
- **`models.py`** — Node, Edge, Wave, Triple, MemoryState (see above).

---

## 5. Ingestion (`src/ingestion/`)

- **`llm_extract.py`** — TripleExtractor (regex and/or Hugging Face); suggest_search_terms. Config: configs/llm.yaml.
- **`extraction_pipeline.py`** — extract_from_texts (triples → nodes, waves, relates, in_wave); load_into_graph (optional global_merge); _read_texts_from_path (txt or parquet). CLI: `python -m src.ingestion.extraction_pipeline --input-path <path> [--live] [--global-merge]`.
- **`spark_read_dumps.py`** — Spark text → parquet.
- **`ingestion_online.py`** — stream_ingest, web_search, low-coherence trigger.

Scripts: **acquire_dumps.py** (--source sample | wikipedia-api | wikipedia-sample), **run_spark_etl.py**, **run_batch_ingestion.py**, **run_ingestion_pipeline.py**.

---

## 6. Reasoning (`src/reasoning/`)

- **`loop.py`** — run_reasoning_loop(query, config_root, live): cache → extract query terms → retrieve_graph_context → tension → hypotheses → cache; optional reasoning wave + in_wave persistence. retrieve_graph_context uses NebulaGraphClient snapshot with label_keywords, cluster_ids, limits from reasoning.yaml.
- **`tension.py`** — compute_tension(positions, expected_distances) → TensionResult.
- **`cache.py`** — CacheAdapter (Redis when cache_enabled in reasoning.yaml).
- **`reflection.py`** — run_reflection (tension → meta-waves, hypothesis nodes).
- **`goal_generator.py`**, **`curiosity.py`**, **`simulation_sandbox.py`**, **`self_reflection.py`**, **`prediction.py`** — Used by demo_loop when enabled.

Script: **run_reasoning_demo.py** (--query "...", --live).

---

## 7. Simulation (`src/simulation/`)

- **`gravity.py`** — build_state, compute_forces, update_positions; config from simulation.yaml.
- **`loop.py`** — run_simulation_step (one physics step + domain detection), run_from_graph (snapshot from Nebula → step → optional update_nodes).

Script: **run_simulation.py** (--live, --node-limit, --edge-limit).

---

## 8. Cognition loop (`src/agi_loop/`)

- **`demo_loop.py`** — run_demo(): load/build graph → ticks: spread activation, memory_tick, optional gravity, optional self-reflection/goal/curiosity/sandbox/compression. CLI: --dry-run, --seed-labels, --ticks, --enable-forces, --export-dot, etc.

---

## 9. Physics and monitoring

- **`src/physics/forces.py`** — attraction, repulsion, spring; FAISS approx; Fruchterman-Reingold, SOM (MiniSom).
- **`src/monitoring/metrics.py`** — Prometheus stubs.

---

## 10. Scripts summary

| Script | Purpose |
|--------|--------|
| **goat_ts_gui.py** | **Main Streamlit GUI** — Setup Wizard (deps, Docker, connect, schema), Config Editor, Data Ingestion, Simulation & Physics, Reasoning Loop, Monitoring & Debug, Export & API. Run: `python -m streamlit run scripts/goat_ts_gui.py`. |
| **apply_schema.py** | Apply NebulaGraph schema. --live (required for DB), --reset (drop and recreate space). |
| **acquire_dumps.py** | Acquire corpus text. --source sample | wikipedia-api | wikipedia-sample, --output-dir, --max-docs. |
| **run_spark_etl.py** | Spark ETL: text → Parquet (value column). Requires JAVA_HOME. |
| **run_batch_ingestion.py** | Acquire + optional Spark ETL + extraction. --acquire, --spark-etl, --live. |
| **run_ingestion_pipeline.py** | Full pipeline: acquire → [Spark] → extract → load. |
| **run_reasoning_demo.py** | Run reasoning on a query. --query "...", --live. |
| **run_simulation.py** | One simulation step from graph. --live, --node-limit, --edge-limit. |
| **generate_sample_100k.py** | Synthetic nodes/edges. --node-count, --edge-count, --live. |
| **dump_graph_stats.py** | Node/edge/wave counts. --live. |
| **export_subgraph.py** | Export subgraph by concept. --concept "X", --hops, --output, --plot, --dot, --live. |
| **query_wave.py** | List waves or concepts in a wave. --list, --wave-id, --live. |
| **run_gravity_demo.py** | Gravity demo (no DB write). --live, --iterations, --output, --plot. |
| **streamlit_viz.py** | Lightweight Streamlit app: short demo or graph stats. |
| **serve_api.py** | FastAPI: /run_demo, /reasoning, /health. Run: uvicorn scripts.serve_api:app --host 0.0.0.0 --port 8000. |
| **goat_ui.py** | Optional Tk-based UI (installer/dashboard). |

---

## 11. Configuration (`configs/`)

| File | Contents |
|------|----------|
| **graph.yaml** | NebulaGraph: host, port, space, username, password, dry_run, batch_size, etc. |
| **reasoning.yaml** | cache_enabled, redis_host, redis_port, cache_ttl_s, node_limit, edge_limit. |
| **simulation.yaml** | gravitational_constant, damping, use_gpu, etc. |
| **llm.yaml** (optional) | enable_model_inference, model_name, device (for extraction). |

---

## 12. Tests (`tests/`)

- **test_placeholder.py** — Basic smoke test (no Docker).
- **milestone_roadmap_stage1.py**, **stage2** — Roadmap stage tests.
- **test_benchmarks_step6.py** — Consistency, reasoning (PuLP), efficiency, interpretability (Graphviz).
- **test_serve_api.py** — API health and endpoints.
- **test_phase1_graph.py**, **test_llm_extract.py**, **test_reasoning_***, **test_physics.py** — Graph, extraction, reasoning, physics.

Run: **`python -m pytest -q`** (or **-v**). From repo root. See [CONTRIBUTING.md](CONTRIBUTING.md).

---

## 13. Quick “what do I run?”

See [README.md](README.md) for full usage. Summary:

- **GUI (recommended):** `python -m streamlit run scripts/goat_ts_gui.py` → Setup Wizard → Check system → complete steps → use Config, Ingestion, Simulation, Reasoning, etc.
- **CLI cognition loop:** `python -m src.agi_loop.demo_loop --dry-run --seed-labels concept --ticks 10`
- **Start stack:** `docker compose -f docker/docker-compose.yml up -d`
- **Schema:** `python scripts/apply_schema.py --live`
- **Reasoning:** `python scripts/run_reasoning_demo.py --live --query "your query"`
- **Tests:** `python -m pytest -q`
