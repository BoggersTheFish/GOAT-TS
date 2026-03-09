# Changelog

This file summarizes **notable documentation and feature alignment changes**. For the development roadmap and stage-by-stage history see [ROADMAP.md](ROADMAP.md). For technical compliance (Steps 1–7) see [README_ARCHITECTURE.md](README_ARCHITECTURE.md).

---

## Documentation overhaul (current)

All README and documentation files were **fully rewritten** to describe the **system we currently have**: what it does, how it’s used, and why it’s useful.

- **README.md** — Defines the system (knowledge-graph–driven cognition scaffold), what it does (ingest → graph → cognition loop → reasoning), why it’s useful, and how to use it (GUI first: Setup Wizard with “Check system,” then Config, Ingestion, Simulation, Reasoning, Monitoring, Export & API). Includes quick start, cognition loop CLI, HTTP API, config, ingestion/reasoning commands, Thinking Wave graph, and doc index.
- **README_ARCHITECTURE.md** — Technical architecture reference: ingestion, graph storage, physics/simulation, reasoning, cognition loop, monitoring/deployment, implemented-vs-baseline summary, key scripts/configs, compliance summary, minimal cognition cycle.
- **CODEBASE.md** — Codebase reference: layout, data models, graph layer, ingestion, reasoning, simulation, cognition loop, physics/monitoring, scripts summary (including **goat_ts_gui.py** as main Streamlit GUI), configs, tests, quick “what do I run?”
- **PLATFORM.md** — Portability: what the code assumes (paths, subprocess, Docker), per-OS notes (Windows PowerShell, venv, `;` not `&&`), how to verify, optional Git line endings.
- **CONTRIBUTING.md** — How to contribute, development rules, cross-platform, sanity check, test suites, scope and roadmap.
- **ROADMAP.md** — Five-stage roadmap with “what’s implemented” and how to run/test each stage; points to README for daily usage.
- **examples/README.md** — Sample input, export shape, API request examples, environment/credentials; links to main README.
- **CHANGELOG.md** — This file: doc/feature change summary.

---

## Features (see README_ARCHITECTURE)

The current system implements: ingestion (acquire, Spark ETL, extraction, global merge), graph (NebulaGraph client, schema, FAISS vector backend, cluster merge), activation and memory (spreading activation, decay, state transitions), cognition loop (demo_loop with optional forces, self-reflection, goal generator, curiosity, sandbox, compression), reasoning (retrieve context, tension, hypotheses, Redis cache), simulation (gravity, run_from_graph, domain detection), reflection and self-reflection, consolidation and abstraction, prediction, online learning and query handler, noise filter, benchmarks (Step 6), Step 7 capabilities (goal generator, curiosity, sandbox, long-term self-reflection, compression), API (serve_api), and UIs (goat_ts_gui.py Streamlit full GUI, streamlit_viz.py, optional goat_ui.py Tk).
