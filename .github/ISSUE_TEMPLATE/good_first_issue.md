---
name: Good first issue
description: Smaller tasks ideal for new contributors
title: "[Good first issue] "
labels: ["good first issue"]
assignees: []
---

**Task**
One of the following (or similar):

- **Add a benchmark case** — Add one entry to `examples/benchmarks.json` (synthetic tension, CommonsenseQA-style, or contradiction) and optionally run `python scripts/run_benchmarks.py --max-cases 1` to confirm.
- **Improve viz hover** — In `scripts/streamlit_viz.py` interactive graph, add or refine hover text (e.g. show activation + label in tooltip).
- **Docstring or README fix** — Fix a typo, clarify a command, or add one example to README or TROUBLESHOOTING.
- **Test for a script** — Add a small pytest that runs a script with `--dry-run` or `--help` and asserts exit code 0.

**Acceptance**
- Change is small and scoped.
- `python -m pytest -q` still passes.
- PR references this issue.

**References**
- [CONTRIBUTING.md](https://github.com/BoggersTheFish/GOAT-TS/blob/main/CONTRIBUTING.md)
- [ROADMAP.md](https://github.com/BoggersTheFish/GOAT-TS/blob/main/ROADMAP.md)
