# Hacker News draft

**Title:** GOAT-TS – Graph-based cognitive scaffold: spreading activation, tension reasoning, local-first (Show HN)

**Post (for comment or “Show HN” text):**

GOAT-TS is an open-source **knowledge-graph–driven cognition scaffold** [0]. You ingest text into a graph (concepts + relations), run spreading activation and memory decay (ACT-R style), then reason over “tension” — mismatches between where nodes are and where they’re expected to be — to produce hypotheses. The key idea: reasoning is **traceable** (activated subgraphs, high-tension pairs, waves) instead of a single LLM black box.

Features:
- **Local-first:** dry-run without Docker; add NebulaGraph/Redis/Spark when you need scale.
- **Config-driven:** YAML for graph, reasoning, simulation, LLM (HuggingFace/Ollama/LangChain).
- **Extras:** goal-directed seeding, curiosity (e.g. Wikipedia/arXiv), optional gravity simulation, Streamlit GUI, FastAPI, Prometheus/Grafana stubs.
- **Benchmarks:** small suite comparing GOAT vs a simple LLM baseline (accuracy proxy, tension, latency).

Stack: Python 3.11+, NebulaGraph, PyTorch, Streamlit. MIT. I’d be glad for feedback from anyone interested in graph-based reasoning or interpretable AI.

[0] https://github.com/BoggersTheFish/GOAT-TS

---

*Submit as “Show HN: GOAT-TS – Graph-based cognitive scaffold (spreading activation, tension reasoning)”. Keep the post concise; expand in comments if needed.*
