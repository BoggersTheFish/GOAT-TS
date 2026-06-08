# GOAT-TS v0.1.0

GOAT-TS is a small, deterministic, receipt-first **graph cognition kernel**.
It turns bounded text claims into candidate graph updates, carries provenance
through every accepted update, runs transparent cognition stages, and records
the complete result in a JSON receipt.

GOAT-TS does not claim to be AGI. Parsed or generated claims are candidates,
not truth.

## v0.1 Scope

The supported pipeline is:

```text
input
  -> candidate claims + repair targets
  -> provenance-carrying graph
  -> spreading activation
  -> memory states
  -> tension scores
  -> deterministic JSON receipt
```

The bounded parser accepts one claim per line in these forms:

- `X is Y`
- `X has Y`
- `X uses Y`
- `X supports Y`

Anything else becomes a `RepairTarget`; it is never silently discarded.

The core has no runtime dependencies and does not use NebulaGraph, Redis,
Spark, Streamlit, LangChain, Transformers, Torch, FAISS, Kubernetes, optional
databases, GUIs, LLMs, plugins, or web ingestion.

## Run

Python 3.11 or newer is required.

```bash
python -m pytest -q
python -m goat_ts.cli demo \
  --input examples/sample.txt \
  --out artifacts/demo_receipt.json
```

Running the demo repeatedly with the same command and input produces the same
receipt bytes.

## Package Layout

```text
goat_ts/
  core/       # data contracts, deterministic IDs, in-memory graph
  ingest/     # bounded candidate-claim parser
  engine/     # activation, memory, and tension
  receipts/   # deterministic JSON writer
  cli.py      # receipt-producing demo
```

## Rehaul Boundary

`goat_ts/`, `tests/v01/`, `examples/sample.txt`, and `pyproject.toml` define the
v0.1 implementation. Existing `src/`, infrastructure, scripts, configurations,
and legacy tests are retained only as historical material during the rehaul.
They are not dependencies of v0.1 and are excluded from its test collection.

Future capabilities must preserve the v0.1 rules: deterministic behavior,
mandatory provenance, explicit repair targets, and receipts for every demo or
evaluator.
