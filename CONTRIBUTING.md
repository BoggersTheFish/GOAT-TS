# Contributing to GOAT-TS

Thanks for your interest in contributing. These guidelines help keep the repo consistent and easy to work with.

## Documentation and overview

- **Setup and usage:** [README.md](README.md)
- **Architecture and compliance:** [README_ARCHITECTURE.md](README_ARCHITECTURE.md)
- **Development roadmap:** [ROADMAP.md](ROADMAP.md)
- **Codebase reference:** [CODEBASE.md](CODEBASE.md)
- **Portability:** [PLATFORM.md](PLATFORM.md)

## How to contribute

1. **Open an issue** for bugs, feature ideas, or questions. Describe what you’re trying to do and (for bugs) steps to reproduce.
2. **Fork the repo** and create a branch (e.g. `fix/issue-123` or `feat/add-xyz`).
3. **Make changes** following the development rules below.
4. **Run tests** from repo root: `python -m pytest -q` (or `-v` for verbose). Fix or skip failing tests and document why.
5. **Open a pull request** with a clear title and description; reference any related issues.

## Development rules

- **Prefer `--dry-run` first.** For scripts that support it (e.g. `apply_schema.py`), run with `--dry-run` before using `--live`.
- **Use `--live` only when infra is up.** Start services with `docker compose -f docker/docker-compose.yml up -d` (or `.\scripts\start-local.ps1` on Windows) before any `--live` command.
- **Commit often.** Small, focused commits (e.g. `fix: apply_schema dry-run`, `feat: add streamlit viz`) make history easier to follow.
- **No silent fallbacks.** If a dependency is required (e.g. APScheduler, Spark), document it and fail or skip explicitly; see [ROADMAP.md](ROADMAP.md).

## Cross-platform

The project targets **Windows, macOS, and Linux**. Use `pathlib.Path`, avoid `shell=True` in subprocess, and run Python as `python scripts/...` or `python -m pytest` from repo root. See [PLATFORM.md](PLATFORM.md) for how portability is maintained.

## One-command sanity check

After clone and `pip install -r requirements.txt`:

```bash
python scripts/apply_schema.py --dry-run
python -m pytest tests/test_placeholder.py -v
```

Both should succeed without Docker or NebulaGraph.

## Test suites

- **Smoke:** `python -m pytest -q`
- **Roadmap Stage 1:** `python -m pytest tests/milestone_roadmap_stage1.py -v`
- **Roadmap Stage 2:** `python -m pytest tests/milestone_roadmap_stage2.py -v`
- **Benchmarks (Step 6):** `python -m pytest tests/test_benchmarks_step6.py -v`
- **API:** `python -m pytest tests/test_serve_api.py -v`

See [pytest.ini](pytest.ini) for options and ignored modules.

## Scope and roadmap

Development follows the [ROADMAP.md](ROADMAP.md) stages (core loop → online learning/reflection → distributed/GPU → advanced/Streamlit → benchmarks/API/docs). New features should align with the architecture in [README_ARCHITECTURE.md](README_ARCHITECTURE.md) and the module boundaries in [CODEBASE.md](CODEBASE.md).
