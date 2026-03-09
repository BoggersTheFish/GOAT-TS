# GOAT-TS Reverse-Engineered Architecture Baseline

This document captures the current architecture of the GOAT-TS repository as verified for alignment with the specified baseline before any AGI-engine upgrades. Repository: https://github.com/BoggersTheFish/GOAT-TS (local path: GOAT).

---

## 1. Ingestion Pipeline

- **Acquisition**
  - `scripts/acquire_dumps.py`: Downloads or generates corpus text (`--source sample | wikipedia-api | wikipedia-sample`), writes to `data/raw/` (e.g. `wikipedia/abstracts.txt`). Uses Wikipedia REST API or built-in samples.
  - `scripts/generate_sample_100k.py`: Generates synthetic graph data (nodes + edges) for testing; can write to NebulaGraph with `--live`.
- **ETL**
  - `scripts/run_spark_etl.py`: Reads text (e.g. one chunk per line), writes Parquet with a `value` column. Default input `data/raw/wikipedia/abstracts.txt`, output `data/processed/corpus.parquet`. Requires Java / Spark.
- **Extraction**
  - `src/ingestion/extraction_pipeline.py`: Consumes `.txt` or Parquet (with `value` column). Uses regex and/or LLM (`src/ingestion/llm_extract.py`, TripleExtractor) to produce triples. Builds **waves**, **nodes** (concepts + cluster/topic nodes), **relates** and **in_wave** edges. Node IDs from `stable_node_id()` (SHA1 truncated to 16 chars). Writes to NebulaGraph when `--live`.
  - Cluster/topic nodes use label prefix `topic: `. Per-chunk clustering (context-scoped node IDs like `topic_id:subject`).
- **Support**
  - `src/ingestion/spark_read_dumps.py`, `src/ingestion/memory_init.py`, `scripts/run_batch_ingestion.py`, `scripts/run_ingestion_pipeline.py` tie acquire/ETL/extraction together.

---

## 2. Graph Storage (NebulaGraph)

- **Client**
  - `src/graph/client.py`: `NebulaGraphClient` loads config from `configs/graph.yaml` (and `.env` overrides). Dry-run mode uses in-memory `InMemoryGraphStore`. Live mode connects to NebulaGraph (host, port, user, password, space `ts_graph`).
- **Schema**
  - `src/graph/schema/create_space.ngql`: Space `ts_graph`, `vid_type = FIXED_STRING(64)`.
  - `src/graph/schema/create_schema.ngql`:
    - **Tag `node`**: `label` (string), `mass` (double), `activation` (double), `state` (string), `cluster_id` (string), `metadata` (string, JSON).
    - **Tag `wave`**: `label`, `source`, `intensity`, `coherence`, `tension`, `source_chunk_id`.
    - **Edge `relates`**: `weight` (double).
    - **Edge `in_wave`**: `weight` (double).
  - Tag indexes: `node_label_index`, `node_state_index`, `wave_source_index`, `wave_source_chunk_index`. **No vector type or vector index** in schema.
- **Models**
  - `src/graph/models.py`: `Node` (node_id, label, mass, activation, state, cluster_id, embedding, position, velocity, metadata; optional node_type in metadata), `Edge`, `Wave`, `Triple`, `MemoryState` (ACTIVE/DORMANT/DEEP). Embeddings stored in node metadata, not as a dedicated Nebula property.

---

## 3. Physics / Simulation Stubs

- **Forces**
  - `src/physics/forces.py`: `attraction_force`, `repulsion_force`, `spring_force` (NumPy). Pairwise O(n²) style (no FAISS/ANN).
- **Gravity**
  - `src/simulation/gravity.py`: `build_state`, `compute_forces`, `update_positions` using forces and `src/physics/simulation.py` integration. Config from `configs/simulation.yaml`.
- **Simulation loop**
  - `src/simulation/loop.py`: `run_simulation_step`, `run_from_graph` (snapshot from Nebula, run one step, optionally persist). Mass updates, domain detection (Louvain), no spreading activation.

---

## 4. Reasoning Stubs

- **Loop**
  - `src/reasoning/loop.py`: Query → activate nodes (keyword/triple match), fetch subgraph, run gravity/tension, generate hypotheses from tension, optional LLM. Returns `ReasoningResponse` (activated_nodes, hypotheses, tension, graph_context). Uses graph client and reasoning config.
- **Tension**
  - `src/reasoning/tension.py`: `compute_tension(positions, expected_distances)` → `TensionResult` (score, high_tension_pairs). Position-based, no contradiction detection on relations.
- **Cache**
  - `src/reasoning/cache.py`: `CacheAdapter` backed by Redis when `cache_enabled` in `configs/reasoning.yaml`; otherwise no-op. Get/set with TTL.

---

## 5. Monitoring and Deployment

- **Monitoring**
  - `src/monitoring/metrics.py`: Prometheus metrics stubs.
- **Deployment**
  - `docker/`: Docker Compose for NebulaGraph, Redis, Spark.
  - `infra/`: Present; Terraform/Ansible not verified in detail.

---

## 6. Implemented vs Missing (vs Spec)

| Area | Implemented | Missing |
|------|-------------|--------|
| Graph/node structures | ✓ Tags node/wave, edges relates/in_wave, mass/activation/state | Vector indexes; global concept merging |
| Persistent memory | ✓ Nebula + in-memory fallback | SQLite backup; auto state transitions; graph versioning |
| Partial activation | ✓ Attributes (activation, mass) | Full propagation; spreading activation; wave interference |
| AGI loop | ✓ Stubs (reasoning loop, tension, hypotheses) | Loop integration with propagation; learning/adaptation |
| Learning | ✓ Ingestion only | Feedback; contradiction resolution; reweighting |
| Abstraction / prediction | ✗ | Concept abstraction; prediction generation; self-reflection |
| Scalability / response gen | ✗ | Distributed execution; formal response generation pipeline |

---

## 7. File and Dependency Summary

- **Key scripts**: `apply_schema.py`, `acquire_dumps.py`, `generate_sample_100k.py`, `run_spark_etl.py`, `run_simulation.py`, `run_reasoning_demo.py`, `export_subgraph.py`, `dump_graph_stats.py`, `query_wave.py`, `run_gravity_demo.py`, `goat_ui.py`.
- **Dependencies**: nebula3-python, langchain, transformers, torch, numpy, networkx, matplotlib, pyyaml, python-dotenv, requests, tqdm, sentence-transformers; optional: pyarrow, pyspark, redis, prometheus-client.
---

## 8. Post–Step 1 Updates (Vector Backend and Global Merge)

- **Vector index**: External backend via **FAISS** (`src/graph/vector_index.py`). Embeddings stay in node metadata in Nebula; no Nebula vector type. `EmbeddingVectorIndex` supports add, search_by_threshold, search_knn, find_similar_pairs, save/load.
- **Global concept merging**: `src/graph/cluster_merge.py` runs after extraction: cosine similarity > 0.8 (configurable), merge nodes (combine mass, average activation, union edges) using the FAISS index. Invoked with `--global-merge` (and `--merge-threshold`) in the extraction pipeline.
- **Node IDs**: Switched to **UUIDv5** (namespace + seed) in `extraction_pipeline.stable_node_id` for collision avoidance; VID remains within Nebula `FIXED_STRING(64)`.
- **Requirements**: `faiss-cpu>=1.7.4` added. Cluster merge uses `sentence-transformers` for embedding when metadata has none.
- **Config**: `configs/graph.yaml` may specify `embedding_model` for cluster merge; pipeline passes `config_root` for merge.

---

## 9. Quick Demo: Running a Cognition Cycle

A minimal standalone demo runs a multi-tick TS cognition cycle using spreading activation, memory decay/state transitions, and optional gravity. Use it as a sanity check and integration test for activation, memory, and forces.

**Run (in-memory, no Nebula):**

```bash
python -m src.agi_loop.demo_loop --dry-run --ticks 20
```

With seeds by label and optional Graphviz export:

```bash
python -m src.agi_loop.demo_loop --dry-run --seed-labels "concept,apple" --ticks 15 --export-dot out/demo.dot --verbose
```

**CLI options:**

| Option | Description |
|--------|-------------|
| `--graph-space` | Nebula space name (default from config). |
| `--seed-labels` | Comma-separated label keywords (e.g. `apple,fruit`). |
| `--seed-ids` | Comma-separated node IDs. |
| `--ticks` | Number of simulation ticks (default 20). |
| `--decay-rate` | Memory decay per tick (default 0.95). |
| `--enable-forces` | Run one gravity step each tick (FAISS-approx when n≥200). |
| `--export-dot` | Write a Graphviz `.dot` file at end (nodes by state: green=ACTIVE, gold=DORMANT, gray=DEEP). |
| `--verbose` | More logging. |
| `--dry-run` | Use in-memory store; if empty, a synthetic graph is generated. |

**Per-tick cycle:** (1) Spread activation from seed nodes (ACT-R style, `activation.py`), (2) memory tick (decay + state transitions + DEEP promotion via `memory_manager.memory_tick`), (3) optional gravity step (`gravity.build_state` → `compute_forces` → `update_positions`), (4) log ACTIVE/DORMANT/DEEP counts, top activations, coherence/tension stubs, (5) persist node updates to Nebula unless `--dry-run`.

**Sample output (excerpt):**

```
Tick 1/20: ACTIVE=39 DORMANT=1 DEEP=0 | coherence=0.8019 tension=68.82
  Top activated: [('2564a10c-8f6…', 0.184), ...]
...
Done. Ticks=20, Seeds=20, Final ACTIVE=... DORMANT=... DEEP=...
```

**Error handling:** The script is strict: missing seeds, failed Nebula connection, or missing modules raise clear exceptions and exit(1). Use `--dry-run` to avoid Nebula when not available.
