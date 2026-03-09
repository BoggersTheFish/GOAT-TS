# GOAT Codebase Reference

**Author:** Ben Michalek (BoggersTheFish)

This document explains what each part of the GOAT (Thinking System) codebase does and where to find it. Use it to navigate the repo and understand how components fit together.

---

## 1. Overview

GOAT is a **local-first scaffold** for a knowledge-graph–driven “Thinking System”: text is ingested into a graph (NebulaGraph), then **reasoning** (query → subgraph → tension → hypotheses) and **simulation** (gravity-style mass/activation updates, clustering) run over that graph. The stack supports dry-run (in-memory) and **live** mode (real NebulaGraph, Redis, Spark).

**High-level flow:**

1. **Ingestion:** Acquire text → extract subject-relation-object triples → insert **nodes**, **waves**, and **edges** into the graph.
2. **Reasoning:** Given a query, retrieve a relevant subgraph, compute “tension” between node positions vs. expected distances, and produce **hypotheses** (e.g. “What evidence explains the conflict between X and Y?”). Optionally persist reasoning waves and cache results in Redis.
3. **Simulation:** Load a subgraph from NebulaGraph, run a gravity-based physics step (forces, positions, mass updates), detect communities (domains), then **write updated masses/activations/cluster_id** back to the graph.

---

## 2. Repository Layout

```text
GOAT/
├── configs/           # YAML config for graph, LLM, reasoning, simulation
├── docker/            # Docker Compose for NebulaGraph, Redis, Spark
├── infra/             # Terraform and Ansible (deployment scaffolding)
├── scripts/           # Entry-point scripts (schema, load data, demos, ingestion pipeline)
├── src/               # Core Python packages
│   ├── graph/         # Graph models, Nebula client, schema, cognition ontology
│   ├── ingestion/     # Triple extraction, extraction pipeline, Spark reader
│   ├── reasoning/     # Reasoning loop, tension, cache (Redis)
│   ├── simulation/    # Gravity simulation and graph-backed run
│   ├── physics/       # Forces and simulation helpers
│   ├── monitoring/    # Metrics (Prometheus) and dashboards
│   └── utils.py       # Config loading and shared helpers
├── tests/             # Pytest suite (milestones, graph, LLM, reasoning, physics)
├── requirements.txt
├── pytest.ini         # Pytest options (e.g. ignore legacy test module)
├── README.md          # Quick start and phase milestones
└── CODEBASE.md        # This file
```

---

## 3. Core Data Models and Graph Ontology

### 3.1 Models (`src/graph/models.py`)

- **`Node`** – Concept or topic vertex: `node_id`, `label`, `mass`, `activation`, `state` (active/dormant/deep), `cluster_id`, `embedding`, `position`, `velocity`, `metadata`, etc. Used everywhere (ingestion, reasoning, simulation).
- **`Edge`** – Directed edge: `src_id`, `dst_id`, `relation` (e.g. `relates`, `in_wave`), `weight`, `metadata`.
- **`Wave`** – One cognitive episode (one ingestion chunk or one reasoning pass): `wave_id`, `label`, `source` (e.g. `ingestion` / `reasoning`), `intensity`, `coherence`, `tension`, `source_chunk_id`. Stored as its own vertex type in NebulaGraph.
- **`Triple`** – Subject–relation–object from extraction: `subject`, `relation`, `object`, `confidence`.
- **`MemoryState`** – Enum: `ACTIVE`, `DORMANT`, `DEEP`.
- **`NodeType`** – Enum: `KNOWLEDGE`, `QUESTION`, `HYPOTHESIS`, etc. (used in metadata).

### 3.2 Cognition Ontology (`src/graph/cognition.py`)

Defines the **Thinking Wave** layer:

- **`relates`** – Concept-to-concept edges (and concept–cluster).
- **`in_wave`** – Edge from a concept **node** to a **wave** vertex (provenance: “this concept appeared in this chunk/reasoning pass”).
- **`WAVE_SOURCE_INGESTION`** / **`WAVE_SOURCE_REASONING`** – Values for `Wave.source`.

So: **nodes** = concepts/topics; **waves** = episodes; **relates** = concept graph; **in_wave** = which concepts belong to which episode.

---

## 4. Graph Layer (`src/graph/`)

### 4.1 NebulaGraph Client (`src/graph/client.py`)

- **`InMemoryGraphStore`** – In-memory fallback when `dry_run` is true (tests, no DB).
- **`NebulaGraphClient`** – Main client. Reads `configs/graph.yaml`; if `dry_run` is false, connects to NebulaGraph and uses space `ts_graph`.
  - **Insert:** `insert_nodes()`, `insert_edges()`, `insert_waves()` – batch insert with optional progress callbacks.
  - **Update:** `update_nodes()` – writes `mass`, `activation`, `state`, `cluster_id`, `metadata` (used by simulation to persist results).
  - **Read:** `get_node()`, `get_wave()`, `list_nodes()`, `list_edges_between()`, `list_waves()`, `list_cluster_nodes()`, `list_in_wave_edges()`, `neighbors()`, etc.
  - **Snapshots:** `snapshot()` – subgraph by limits and optional label/cluster filters; `snapshot_induced_by_edges()` – edge-first subgraph (used by simulation).

All scripts that talk to the graph use this client; pass `dry_run_override=False` for **live** mode.

### 4.2 Schema (`src/graph/schema/`)

- **`create_space.ngql`** – Creates space `ts_graph` (partitions, replica factor, `vid_type`).
- **`create_schema.ngql`** – Creates tags `node` and `wave`, edges `relates` and `in_wave`, and indexes (e.g. on `node.label`, `node.state`, `wave.source`).

Applied by **`scripts/apply_schema.py`** (use `--live`; optional `--reset` to drop and recreate the space).

### 4.3 Graph Engine and Constraints (`src/graph/graph_engine.py`, `src/graph/constraints.py`)

- **`CognitiveGraph`** – In-memory graph used for semantic layout and similarity (e.g. auto-connect by embedding similarity). Used by some tests and optional flows.
- **Constraints** – Logic that can be wired for graph consistency or layout (see files for details).

---

## 5. Ingestion (`src/ingestion/`)

### 5.1 Triple Extraction (`src/ingestion/llm_extract.py`)

- **`TripleExtractor`** – Extracts (subject, relation, object) from text.
  - If `configs/llm.yaml` has `enable_model_inference: true`, can use a Hugging Face `text2text-generation` pipeline.
  - Otherwise uses **regex fallback** (pattern like `Subject is/has/uses Object`).
- **`suggest_search_terms()`** – Suggests extra search terms for a query (used by reasoning to expand retrieval).
- **Config:** `configs/llm.yaml` – `enable_model_inference`, `model_name`, `device`, etc.

### 5.2 Extraction Pipeline (`src/ingestion/extraction_pipeline.py`)

- **`extract_from_texts()`** – For each text chunk: run `TripleExtractor`, then build **cluster node**, **concept nodes**, **relates** edges, one **Wave** per chunk, and **in_wave** edges (concept → wave). Can prune to `max_nodes_per_label` per label.
- **`load_into_graph()`** – Calls `extract_from_texts()`, then uses **`NebulaGraphClient`** to insert nodes, waves, and edges (when `live=True`).
- **`_read_texts_from_path()`** – Loads chunks from a `.txt` file (one per line) or from **parquet** (column `value`), so Spark output can be fed in directly.
- **CLI:** `python -m src.ingestion.extraction_pipeline --input-path <file or parquet> [--live] [--no-clusters] [--max-nodes-per-label N]`

### 5.3 Spark Reader (`src/ingestion/spark_read_dumps.py`)

- Reads a path (file or directory) as text via **Spark** `spark.read.text()`, repartitions, and writes **parquet** (e.g. for downstream extraction).
- **CLI:** `python -m src.ingestion.spark_read_dumps --input-path <path> --output-path <parquet path>`

### 5.4 Dump Acquisition (`scripts/acquire_dumps.py`)

- **`--source sample`** – Writes built-in sentences to `data/raw/wikipedia/abstracts.txt`.
- **`--source wikipedia-api`** – Fetches Wikipedia article summaries via REST API.
- **`--source wikipedia-sample`** – Can download/parse an XML dump (URL may change).
- Output: `data/raw/wikipedia/abstracts.txt` (or similar). Used as input for Spark or directly for extraction.

### 5.5 Full Ingestion Pipeline (`scripts/run_ingestion_pipeline.py`)

- One script that chains: **acquire** (optional) → **Spark** (optional) → **extraction + load into graph**.
- Example: `python scripts/run_ingestion_pipeline.py --acquire --source sample --live`
- Reads from `configs/graph.yaml` and `configs/llm.yaml` via the extraction pipeline and graph client.

---

## 6. Reasoning (`src/reasoning/`)

### 6.1 Reasoning Loop (`src/reasoning/loop.py`)

- **`run_reasoning_loop(query, config_root, live)`** – Main entry:
  1. **Cache:** If Redis cache is enabled and the query is cached, return cached response.
  2. **Triple extraction** on the query to get “activated” terms from the query itself.
  3. **`retrieve_graph_context(query, config_root, live)`** – Gets a subgraph from NebulaGraph (or dry-run store): by label keywords, cluster IDs, and optionally concepts from **waves** whose label matches the query. Then expands with neighbors and gravity-linked nodes (`_expand_contextual_nodes`, `_gravity_recontextualize`).
  4. **Tension:** Builds positions and expected distances from the subgraph, then **`compute_tension()`** (see below). High tension pairs become **hypotheses** (“What evidence explains the conflict between X and Y?”).
  5. **Cache** – Stores the response in Redis (if enabled).
  6. **Persistence (live only):** Inserts a **reasoning wave** and **in_wave** edges from activated concept nodes to that wave, so the graph records “this query ran and these concepts were activated.”

- **`retrieve_graph_context()`** – Uses **`NebulaGraphClient`** `snapshot()` with `label_keywords`, `cluster_ids`, and optional wave-based expansion. Limits come from **`configs/reasoning.yaml`** (`node_limit`, `edge_limit`).

- **`Hypothesis`** – `prompt` (string) and `rationale` (string).  
- **`ReasoningResponse`** – `query`, `activated_nodes`, `hypotheses`, `tension`, `graph_context`.

### 6.2 Tension (`src/reasoning/tension.py`)

- **`compute_tension(positions, expected_distances)`** – For each pair in `expected_distances`, compares actual Euclidean distance between `positions[src]` and `positions[dst]` to the expected value; sums squared error and returns **`TensionResult`** (score + list of high-tension pairs). Used to drive hypothesis generation.

### 6.3 Cache (`src/reasoning/cache.py`)

- **`CacheAdapter`** – If `configs/reasoning.yaml` has `cache_enabled: true`, uses **Redis** (`redis_host`, `redis_port`) to get/set JSON-serialized reasoning results. TTL from `cache_ttl_s`. Used by the reasoning loop to avoid re-running the same query.

### 6.4 Demo Script (`scripts/run_reasoning_demo.py`)

- Parses `--live` and `--query "..."` and calls **`run_reasoning_loop()`**, then prints a summary dict (query, activated_nodes, tension_score, hypotheses, graph_context, live).  
- **Important:** Always pass the query in the same command, e.g. `python scripts/run_reasoning_demo.py --live --query "Concept 39 Concept 49"` (do not type `--query ...` on a separate line or paste multiple commands on one line).

---

## 7. Simulation (`src/simulation/`)

### 7.1 Gravity Physics (`src/simulation/gravity.py`)

- **`build_state(nodes)`** – Converts nodes to position/mass/velocity arrays.
- **`compute_forces(state, edges, config)`** – Computes forces between nodes (gravity-like, using edge weights and distances).
- **`update_positions(state, forces, config)`** – Integrates forces to update positions and velocities.

Config: **`configs/simulation.yaml`** (e.g. `gravitational_constant`, `epsilon`, `phi`, `kappa`, `lambda`, `max_mass`, `split_threshold`).

### 7.2 Simulation Loop (`src/simulation/loop.py`)

- **`run_simulation_step(nodes, edges, config_path)`** – One physics step: build state → compute forces → update positions → for each node compute mass update and gravity links, then return **updated nodes** (with new mass, state, position, velocity, metadata like `gravity_links`).
- **`detect_domains(nodes, edge_pairs)`** – Uses **NetworkX** Louvain communities to assign a domain/cluster ID per node.
- **`run_from_graph(config_root, live, node_limit, edge_limit)`** – Loads a subgraph from NebulaGraph via **`client.snapshot_induced_by_edges()`**, converts to `Node`/`Edge` objects, runs **`run_simulation_step()`**, then **`detect_domains()`**. If **`live`**, calls **`client.update_nodes(updated_nodes, domain_map=domains)`** to **persist** mass, activation, state, cluster_id (domain), and metadata back to NebulaGraph.

So simulation **does** write back to the graph when `--live` is used.

### 7.3 Demo Script (`scripts/run_simulation.py`)

- **`python scripts/run_simulation.py --live --node-limit 50 --edge-limit 200`** – Runs **`run_from_graph()`** with those limits and prints a summary (updated_nodes, domains, source_nodes, source_edges, live).

---

## 8. Physics Helpers (`src/physics/`)

- **`src/physics/forces.py`** – Force computation helpers.
- **`src/physics/simulation.py`** – Simulation integration helpers.
- Used by the simulation layer and tests.

---

## 9. Monitoring (`src/monitoring/`)

- **`src/monitoring/metrics.py`** – Prometheus metrics (if wired in).
- **`src/monitoring/grafana/`** – Grafana dashboard JSON (e.g. `ts-overview-dashboard.json`).
- **`infra/`** – Terraform and Ansible for deployment; currently scaffolding.

---

## 10. Scripts Summary

| Script | Purpose |
|--------|--------|
| **`scripts/start-local.ps1`** | Starts Docker Compose (NebulaGraph, Redis, Spark). Run from repo root. |
| **`scripts/apply_schema.py`** | Applies NebulaGraph schema. `--live` required for DB; `--reset` drops space and recreates. |
| **`scripts/generate_sample_100k.py`** | Inserts synthetic nodes/edges. `--node-count`, `--edge-count`, `--live`. |
| **`scripts/acquire_dumps.py`** | Downloads or generates corpus text. `--output-dir`, `--source` (sample / wikipedia-api / wikipedia-sample), `--max-docs`, etc. |
| **`scripts/run_ingestion_pipeline.py`** | Full pipeline: acquire → [Spark] → extract → insert. `--acquire`, `--source`, `--use-spark`, `--live`. |
| **`scripts/run_reasoning_demo.py`** | Runs reasoning on a query. `--live`, `--query "..."`. |
| **`scripts/run_simulation.py`** | Runs one simulation step on graph data. `--live`, `--node-limit`, `--edge-limit`. |
| **`scripts/run_batch_ingestion.py`** | Alternative batch ingestion (acquire + optional Spark ETL + extraction). |
| **`scripts/run_spark_etl.py`** | Spark ETL only (text → parquet). |
| **`scripts/goat_ui.py`** | Optional UI entry point. |

---

## 11. Configuration Files (`configs/`)

| File | Contents |
|------|----------|
| **`graph.yaml`** | NebulaGraph connection (host, port, space, username, password), `dry_run`, batch_size, etc. |
| **`llm.yaml`** | LLM/extraction: `enable_model_inference`, `model_name`, `device`. When false, regex fallback is used. |
| **`reasoning.yaml`** | Reasoning: `cache_enabled`, `redis_host`, `redis_port`, `cache_ttl_s`, `hypothesis_count`, `node_limit`, `edge_limit`. |
| **`simulation.yaml`** | Simulation physics: `gravitational_constant`, `epsilon`, `phi`, `kappa`, `lambda`, `max_mass`, `split_threshold`, etc. |

---

## 12. Tests (`tests/`)

- **`test_phase1_graph.py`**, **`milestone_phase1.py`** – Graph client and schema (often dry-run).
- **`test_llm_extract.py`**, **milestone_phase2.py** – Triple extraction.
- **`test_reasoning_memory_first.py`** – Reasoning retrieval and memory-first behavior.
- **`test_physics.py`** – Physics/simulation.
- **`milestone_phase3.py`** … **phase5** – Phase milestones.
- **`test_ts_cognitive_engine.py`** – Depends on external `ts_cognitive_engine` package; **ignored** in `pytest.ini` so the rest of the suite runs.

Run: **`pytest -q`** (or **`python -m pytest -q`**). Ensure one command per line in the terminal (e.g. run `generate_sample_100k.py` and `run_reasoning_demo.py` in **separate** commands).

---

## 13. Quick Reference: “What do I run?”

- **Start stack:** `powershell -ExecutionPolicy Bypass -File ".\scripts\start-local.ps1"`
- **Schema (fresh):** `python .\scripts\apply_schema.py --live --reset` then `python .\scripts\apply_schema.py --live`
- **Load synthetic graph:** `python .\scripts\generate_sample_100k.py --node-count 1000 --edge-count 2500 --live`
- **Reasoning:** `python .\scripts\run_reasoning_demo.py --live --query "Concept 39 Concept 49"`
- **Simulation:** `python .\scripts\run_simulation.py --live --node-limit 50 --edge-limit 200`
- **Ingestion (sample → graph):** `python .\scripts\run_ingestion_pipeline.py --acquire --source sample --live`
- **Tests:** `python -m pytest -q`

For more detail on the full implementation and test plan, see the plan document (e.g. GOAT Full Implementation And Test Plan).
