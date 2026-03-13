# Reddit draft (r/MachineLearning, r/LocalLLaMA, r/artificial)

**Title:** GOAT-TS: Open-source graph-based cognitive scaffold — spreading activation, tension reasoning, local-first (NebulaGraph, PyTorch, Streamlit)

**Body:**

I've been working on a **knowledge-graph–driven cognition scaffold** and just open-sourced it: [GOAT-TS](https://github.com/BoggersTheFish/GOAT-TS).

**What it does:** You ingest text into a graph (concepts + relations), run **spreading activation** and **memory dynamics** (ACT-R style decay, state transitions), then **reason over tension** — i.e. where the graph “disagrees” with expected structure — to produce hypotheses. Optional gravity simulation, goal-directed seeding, and curiosity-driven external queries (e.g. Wikipedia/arXiv) extend the loop.

**Why it’s different from “just an LLM”:** The reasoning is **traceable**: you get activated subgraphs, high-tension pairs, and waves (cognitive episodes) so you can see *why* the system suggested something. It’s **local-first** (dry-run without Docker; NebulaGraph/Redis/Spark when you scale) and config-driven (YAML). There’s a full Streamlit GUI, FastAPI, Prometheus/Grafana stubs, and a small benchmark suite to compare GOAT vs a simple LLM baseline.

**Stack:** Python 3.11+, NebulaGraph, PyTorch, LangChain/Ollama optional, Streamlit, FAISS. MIT licensed.

If you’re into **neuro-symbolic**, **graph reasoning**, or **interpretable AI**, I’d love feedback. Benchmarks and notebooks are in the repo; happy to answer questions.

---

*Suggested subreddits: r/MachineLearning, r/LocalLLaMA, r/artificial. Keep title under 300 chars; body can be trimmed for strict subs.*
