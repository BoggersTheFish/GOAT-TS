## Benchmarks and Evaluation

This document describes the lightweight benchmark suite and how to run it. The
goal is not to beat any specific leaderboard, but to **compare behaviors**:

- GOAT-TS cognition + reasoning loop (with/without goals/curiosity/forces),
- A simple local LLM-style baseline (query-only, no graph), and
- Ablations that toggle key features.

The emphasis is on **traceability** (paths, waves, hypotheses) and **runtime
signals** (tension, coherence, ticks/time) rather than only raw accuracy.

---

## 1. Benchmark cases

Benchmark definitions live in:

- `examples/benchmarks.json` — each entry has:
  - `id` — short identifier
  - `description` — human-readable description
  - `query` — input query or prompt
  - `expected_substring` — phrase that should appear in either hypotheses or
    activated labels for a “hit” (very coarse accuracy proxy)

You can add more cases by appending to this JSON file; the runner picks them up
automatically.

---

## 2. Running the benchmarks

From the repository root:

```bash
python scripts/run_benchmarks.py --max-cases 5 --output examples/benchmarks_out.json
```

Command-line options:

- `--max-cases` — limit the number of benchmark cases to run (default: all).
- `--output` — optional path to write a JSON summary file.

The script always prints a machine-readable JSON summary to stdout. Example:

```bash
python scripts/run_benchmarks.py --max-cases 3 | jq .
```

---

## 3. Metrics

For each case, the runner reports:

- **query** — the input string.
- **expected_substring** — coarse target phrase.
- **goat:**
  - `hit` — `true` if the expected substring appears in any hypothesis prompt
    or in the activated node labels (case-insensitive).
  - `tension_score` — scalar tension value from the reasoning loop.
  - `graph_nodes` / `graph_edges` — size of the retrieved subgraph.
  - `latency_s` — wall-clock time for the `run_reasoning_loop` call.
- **llm_baseline:**
  - `hit` — `true` if the expected substring appears in the LLM output text.
  - `latency_s` — wall-clock time for the baseline call.

The LLM baseline is **best-effort and optional**:

- When `llm.enable_model_inference` is `false` or LLM imports fail, the
  baseline returns an empty or regex-only response and is clearly marked as
  `llm_enabled: false` in the summary.

---

## 4. Ablations

The benchmark runner performs simple ablations over the cognition loop:

- GOAT-TS reasoning (default config, no forces).
- GOAT-TS reasoning + cognition demo with:
  - `--enable-forces`,
  - `--enable-goal-generator`,
  - `--enable-curiosity`.

For each case, the script records:

- `demo_ticks` — number of ticks requested,
- `demo_latency_s` — runtime of the cognition loop for that case,
- `demo_final_states` — aggregate ACTIVE/DORMANT/DEEP counts.

These values can be inspected over multiple runs to understand how forces and
curiosity affect performance and state distributions.

---

## 5. Interpreting results

- **Accuracy (hit rate):** fraction of cases where `hit == true`. The signal is
  intentionally coarse (substring match) and should be read as a **sanity
  check**, not as a leaderboard metric.
- **Interpretability:** GOAT-TS exposes the full reasoning trace:
  - Activated nodes and edges,
  - Tension scores and high-tension pairs,
  - Hypothesis prompts,
  - Waves and in_wave edges (see GUI provenance tracing).
- **Efficiency:** use:
  - `latency_s` and `demo_latency_s` from the benchmark script,
  - Prometheus metrics (`ts_query_latency_seconds`, `ts_simulation_steps_total`,
    `ts_activation_coherence`, `ts_tension_score`) from `/metrics`,
  - Grafana dashboards (see `src/monitoring/grafana/ts-overview-dashboard.json`).

---

## 6. Pytest integration

Additional tests under `tests/` cover:

- Goal-directed seeding (`--goal-labels`) in the cognition loop,
- Curiosity fallbacks (ensuring no exceptions even when graph/web backends are
  unavailable),
- Benchmark runner smoke test (script executes and writes a summary file),
- Streamlit viz import/definition.

Run tests as usual:

```bash
python -m pytest -q
```

Some tests may be skipped when optional dependencies (e.g. PuLP) or LLM
backends are not installed; this is expected and documented in the test
messages.

