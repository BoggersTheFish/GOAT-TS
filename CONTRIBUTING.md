# Contributing to GOAT-TS

Thanks for your interest. These guidelines keep the repo usable as we move from "README-first" to "something runs."

## Cross-platform

The project is written to run on **Windows, macOS, and Linux**. Use `pathlib.Path`, avoid `shell=True` in subprocess, and run Python as `python scripts/...` or `python -m pytest` from repo root. See [PLATFORM.md](PLATFORM.md) for how portability is maintained and how to verify on a new system.

## Development rules

- **Prefer `--dry-run` first.** Scripts that support it (e.g. `apply_schema.py`) should be run with `--dry-run` to see what would happen before using `--live`.
- **Use `--live` only when infra is up.** Run `docker compose -f docker/docker-compose.yml up -d` (or `.\scripts\start-local.ps1` on Windows) before any `--live` command.
- **Commit often.** Small, focused commits (e.g. "feat: minimal nebula connection", "fix: apply_schema dry-run") make progress visible and history easier to follow.
- **Run tests before pushing.** From repo root: `python -m pytest -q`. Fix or skip failing tests and document why.

## One-command sanity check

After clone and `pip install -r requirements.txt`:

```bash
python scripts/apply_schema.py --dry-run
python -m pytest tests/test_placeholder.py -v
```

Both should succeed without Docker or NebulaGraph.

## Scope

- **Phase 0:** Get `apply_schema --live` and one passing test working with minimal deps.
- **Phase 1:** Smallest useful "ingest → graph" (e.g. 5–10 sentences → extract → print or insert).
- **Phase 2+:** Wave + in_wave demo, toy gravity sim, real acquire_dumps.

Start tiny and visible; build momentum from there.
