# GOAT-TS Architecture Reference

This document is the **technical architecture reference** for GOAT-TS: ingestion, graph storage, simulation, reasoning, and compliance with the specified baseline (Steps 1–7). For setup, quick start, and usage see [README.md](README.md).

**Repository:** [github.com/BoggersTheFish/GOAT-TS](https://github.com/BoggersTheFish/GOAT-TS) (local path: GOAT).

---


## 1. Ingestion Pipeline

- **Acquisition**
  - `scripts/acquire_dumps.py`: Downloads or generates corpus text (`--source sample | wikipedia-api | wikipedia-sample`), writes to `data/raw/` (e.g. `wikipedia/abstracts.txt`). Uses Wikipedia REST API or built-in samples.
  - `scripts/generate_sample_100k.py`: Generates synthetic graph data (nodes + edges) for testing; can write to NebulaGraph with `--live`.
- **ETL**
  - `scripts/run_spark_etl.py`: Reads text (e.g. one chunk per line), writes Parquet with a `value` column. Default input `data/raw/wikipedia/abstracts.txt`, output `data/processed/corpus.parquet`. Requires Java / Spark.
- **Extraction**
  - `src/ingestion/extraction_pipeline.py`: Consumes `.txt` or Parquet (with `value` column). Uses regex and/or LLM (`src/ingestion/llm_extract.py`, TripleExtractor) to produce triples. Builds **waves**, **nodes** (concepts + cluster/topic nodes), **relates** and **in_wave** edges. Node IDs from `stable_node_id()` (UUIDv5 namespaced; see §8). Writes to NebulaGraph when `--live`.
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

*Baseline as of Step 1 (reverse-engineered state). Post–Step 1 additions (spreading activation, memory manager, FAISS forces, demo loop) are in §8–9.*

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

---

## 10. Step 2 (Fix Architectural Weaknesses) – Compliance

| Spec item | Status | Notes |
|-----------|--------|--------|
| **Graph: external vector backend** | Done | `src/graph/vector_index.py`: `EmbeddingVectorIndex` (FAISS IndexFlatIP), add/search_knn/search_by_threshold/find_similar_pairs/save/load; embeddings in node metadata; faiss-cpu in requirements. |
| **Global concept merging** | Done | `src/graph/cluster_merge.py`: `global_concept_merge(nodes, edges, threshold)`; filter non–topic nodes, FAISS, union-find, merge mass/activation/edges; `CLUSTER_LABEL_PREFIX` in `cognition.py`; config in `graph.yaml`. |
| **Pipeline integration** | Done | UUIDv5 in `extraction_pipeline.stable_node_id`; `load_into_graph(global_merge, merge_threshold)`; `--global-merge`, `--merge-threshold` CLI. |
| **Propagation logic** | Done | `src/activation.py`: damped spreading (PyTorch/NumPy), max_hops, threshold; `activate_and_propagate`, `get_activated_subgraph`. forces.py: `approximate_neighbor_pairs` (FAISS); gravity uses `use_faiss_approx`, `faiss_k`. (API is in-memory nodes/edges; demo wires client → nodes/edges → activation.) |
| **Memory systems** | Done | `src/memory_manager.py`: `decay_activations`, `transition_states`, `apply_decay_and_transitions`, `promote_to_deep_after_ticks`, `memory_tick`; uses `MemoryState`. |
| **Learning mechanisms** | Done | reasoning/loop: post-wave feedback; high-tension pairs → reweight relates edges (-0.2 via `update_edges`). Client has `update_edges()`. |
| **LLM + confidence filter** | Done | `extract(require_llm=True)`; pipeline filters triples with confidence ≤ min_confidence (default 0.5). CLI: `--require-llm`, `--min-confidence`. |
| **Memory: SQLite / Redis / versioning** | Done | InMemoryGraphStore accepts `sqlite_path`; load/save on init and after mutations. Config: `graph.sqlite_path`. `client.backup_snapshot(path)` for Nebula/versioning. |
| **Other: error handling & concurrency** | Done | extraction_pipeline: try/except with logger.exception around extract_from_texts, global_merge, client init; `--workers N` for multiprocessing extraction. |

---

## 11. Step 3 (Major Upgrades) – Compliance

| Spec item | Status | Notes |
|-----------|--------|--------|
| **Activation wave propagation** (`src/graph/wave_propagation.py`) | Done | `decompose_input`, `propagate_wave` (align ×1.2 / oppose ×0.8 from embedding similarity), `run_wave_propagation`. PyTorch GPU when available. |
| **Node importance weighting** (`src/graph/importance_weighting.py`) | Done | `update_mass_from_activation`; `evolve_edges_with_gat` (PyG GATv2Conv, optional); `apply_importance_weighting`. `torch-geometric` in requirements. |
| **Self-reflection** (`src/reasoning/reflection.py`) | Done | `run_reflection`: post-prop tension, meta-waves (source=reflection), hypothesis nodes (NodeType.HYPOTHESIS). Optional LLM for merge prompts. |
| **Memory consolidation** (`src/graph/consolidation.py`) | Done | `run_consolidation` (merge via cluster_merge, prune mass &lt;0.1, state transitions); `redis_tier_activations`; `schedule_consolidation` (APScheduler job). `apscheduler` in requirements. |
| **Concept abstraction** (`src/graph/abstraction.py`) | Done | `detect_communities_louvain` (NetworkX), `create_super_nodes` (super-nodes + bidirectional relates). |
| **Prediction generation** (`src/reasoning/prediction.py`) | Done | `forward_simulate` (multi-step propagation), `llm_forecast_from_subgraph`, `run_prediction`. |

---

## 12. Step 4 (Integrate Suggested Algorithms) – Compliance

| Spec item | Status | Notes |
|-----------|--------|--------|
| **Spreading activation** (activation.py) | Done | ACT-R with fan-out, damped iter: `act_{t+1} = sum(in)*(1-0.1)+bias` (doc + DEFAULT_DECAY=0.1). |
| **Graph attention** (importance_weighting.py) | Done | GAT **multi-heads** (heads=4), mean over heads for node importance; evolution_scale for edge updates. |
| **Conceptual clustering** (abstraction.py) | Done | **Leiden** via leidenalg/igraph (`detect_communities_leiden`); **hierarchical agglomerative** on embeddings (`detect_communities_hierarchical`, scipy linkage/fcluster). Reqs: leidenalg, igraph, scipy. |
| **Predictive activation** (prediction.py) | Done | **Free-energy**: `predict_activations`, `predictive_activation_error` (predict vs actual, errors, free_energy=0.5*sum(err²)); `backprop_errors_to_edges` (scale weights by error). |
| **Self-organizing structures** (forces.py) | Done | **Fruchterman-Reingold** (`layout_fruchterman_reingold`, `layout_fruchterman_reingold_nx`); **SOM** via **MiniSom** (`layout_som`). Reqs: minisom. |

---

## 13. Step 5 (Learning Mechanisms) – Compliance

| Spec item | Status | Notes |
|-----------|--------|--------|
| **Auto-build from text** (`src/ingestion/ingestion_online.py`) | Done | **Stream mode** (`stream_ingest`), **web_search** (requests; Google Custom Search when API key/CSE_ID set). **Active learning**: low-coherence trigger – when coherence &lt; threshold, run `on_low_coherence` or use last chunk as query, web_search and ingest snippets. |
| **Web search integration** (`src/graph/query_handler.py`) | Done | **Decompose** query (`decompose_query`), **search** (`search_and_fetch` via web_search), **extract triples** and **insert linked waves** (load_into_graph). **TF-IDF relevance** (scikit-learn `TfidfVectorizer` + cosine_similarity) to rank snippets (`tfidf_relevance`). `handle_query` orchestrates. |
| **Higher-level concepts** (abstraction.py) | Done | **Cluster activation patterns** (`cluster_activation_patterns` – KMeans on activation/mass). **PyTorch autoencoders for metas** (`meta_embeddings_autoencoder` – AE on node embeddings, returns node_id → latent vector). |
| **Noise reduction** (`src/graph/noise_filter.py`) | Done | **Discard low-conf** (`filter_low_confidence`). **IsolationForest on tensions** (`tension_outliers_isolation_forest`, `filter_tension_outliers`). **Prune in consolidation**: `run_consolidation(..., noise_filter_min_confidence=..., tension_scores=..., noise_contamination=...)`. Reqs: scikit-learn. |

---

## 14. Step 6 (Benchmarks – Outperformance) – Compliance

Benchmarks in `tests/test_benchmarks_step6.py` ensure consistency, reasoning, efficiency, and interpretability:

| Benchmark | What it does | How to run |
|-----------|--------------|------------|
| **Consistency (path trace)** | Builds a small graph A→B→C, traces path, asserts node/edge alignment and that activation propagates along the path. | `python -m pytest tests/test_benchmarks_step6.py::test_benchmark_consistency_path_trace -v` |
| **Reasoning (PuLP)** | Solves a tiny LP (max 2x+3y s.t. x+y≤1, x,y≥0), asserts optimal value 3.0. | `python -m pytest tests/test_benchmarks_step6.py::test_benchmark_reasoning_pulp -v` (requires `pulp` in requirements.txt). |
| **Efficiency (timings)** | Runs `activate_and_propagate` on a medium graph (~80 nodes), asserts duration &lt; 5 s. | `python -m pytest tests/test_benchmarks_step6.py::test_benchmark_efficiency_timings -v` |
| **Interpretability (Graphviz)** | Calls `export_subgraph_to_dot(data, path)` with a small subgraph; asserts output file exists and contains `digraph`/`graph`. | `python -m pytest tests/test_benchmarks_step6.py::test_benchmark_interpretability_graphviz_export -v` |

Run all four: `python -m pytest tests/test_benchmarks_step6.py -v`. Graphviz export is implemented in `scripts/export_subgraph.py` (`export_subgraph_to_dot`, CLI `--dot`).

---

## 15. Step 7 (New Capabilities) – Compliance

| Capability | Module | Notes |
|------------|--------|--------|
| **Long-term self-reflection** | `src/reasoning/self_reflection.py` | `detect_wave_gaps(waves)`, `generate_goal_nodes_for_gaps(gaps)`, `run_long_term_self_reflection(waves, ...)`. Timer global waves for gaps (time or index); creates `NodeType.GOAL` nodes. |
| **Internal simulation** | `src/reasoning/simulation_sandbox.py` | `clone_subgraph`, `apply_hypothetical_activations/positions`, `run_sandbox_propagation`, `run_sandbox_hypothetical`. Clone subgraph, apply hypotheticals, run propagation without modifying main graph. |
| **Goal generation** | `src/reasoning/goal_generator.py` | `tensions_to_prioritized_questions(tension, id_to_label)`, `goals_from_tension(tension, ...)`. From `TensionResult` high-tension pairs → prioritized questions. |
| **Curiosity-driven exploration** | `src/reasoning/curiosity.py` | `activation_entropy(activations)`, `entropy_reward`, `should_trigger_curiosity_query`, `curiosity_query(query, config_root)`. Entropy rewards; auto-query web via `query_handler.handle_query` when triggered. |
| **Knowledge compression** | `src/graph/compression.py` | `subgraph_to_vector(nodes, edges)` (PyG GNN + global pooling), `compress_and_archive`, `archive_subgraph_to_faiss`. Encode subgraph to vector, add to FAISS index for archive. |

**AGI loop integration** (`src/agi_loop/demo_loop.py`): Optional flags `--enable-self-reflection`, `--self-reflection-interval`, `--enable-sandbox`, `--enable-goal-generator`, `--enable-curiosity`, `--enable-compression`, `--compression-archive`. Goal nodes from self-reflection are inserted and included in the next tick; prioritized questions feed curiosity; compression runs on selected ticks and saves to `--compression-archive` directory.
