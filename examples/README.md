# Examples

This folder contains **sample inputs**, **export shapes**, and **API request examples** for GOAT-TS. For setup and daily usage see the main [README.md](../README.md).

---

## What’s in this folder

- **Sample input** — Example text for the extraction pipeline.
- **Export shape** — Example JSON/PNG/dot output from export and demo.
- **API request examples** — Example request bodies for the HTTP API.
- **Jupyter notebook** — **`goat_end_to_end.ipynb`** runs a full pipeline (load sample → cognition loop with goal seeding → reasoning → summary). Run from repo root: `jupyter notebook examples/goat_end_to_end.ipynb`.
- **Benchmarks** — **`benchmarks.json`** defines benchmark cases; see [BENCHMARKS.md](../BENCHMARKS.md) and `scripts/run_benchmarks.py`.

---

## Sample input

- **`sample_input.txt`** — Sample text (one chunk per line) for the extraction pipeline. Use with **`--input-path examples/sample_input.txt`** (or the full path from repo root).

---

## Export shape

- **`out.json`** / **`export_out.json`** — Example shape of a subgraph export (nodes + edges). To generate real content:

  ```bash
  python scripts/export_subgraph.py --concept "Python" --live --output examples/out.json
  ```

  Add **`--plot examples/out.png`** to generate a 2D layout PNG (requires a live graph with data).

- **Graphviz (.dot):** Use **`--dot examples/out.dot`** with **export_subgraph.py**, or run the cognition loop with **`--export-dot examples/demo_out.dot`**.

---

## API request examples

- **`api_request.json`** — Example request bodies for the HTTP API (see [README.md](../README.md) for how to start the server):

  - **POST /run_demo:** `{"ticks": 5, "dry_run": true, "seed_labels": "concept", "enable_forces": false}`
  - **POST /reasoning:** `{"query": "Wikipedia supports free knowledge...", "live": false}`

  Example with curl:

  ```bash
  curl -X POST http://localhost:8000/run_demo -H "Content-Type: application/json" -d @examples/api_request.json
  ```

  (If the JSON file contains multiple keys, send only the relevant object for the endpoint.)

---

## Environment and credentials

To use Nebula credentials from a file instead of **`configs/graph.yaml`**, copy **`.env.example`** from the repository root to **`.env`** in the root and set:

- **NEBULA_HOST**
- **NEBULA_PORT**
- **NEBULA_USERNAME**
- **NEBULA_PASSWORD**

The graph client loads these via **python-dotenv** and overrides the YAML values.
