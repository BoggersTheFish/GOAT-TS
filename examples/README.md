# Examples

- **sample_input.txt** – Sample text (one chunk per line) you can feed to the extraction pipeline or use with `--input-path`.
- **out.json** – Example shape of a subgraph export (nodes + edges). Real content is produced by:
  ```bash
  python scripts/export_subgraph.py --concept "Python" --live --output examples/out.json
  ```
  Add `--plot examples/out.png` to generate a 2D layout PNG (requires a live graph with data).

To use Nebula credentials from a file instead of `configs/graph.yaml`, copy `.env.example` from the repo root to `.env` and set `NEBULA_HOST`, `NEBULA_PORT`, `NEBULA_USERNAME`, `NEBULA_PASSWORD`.
