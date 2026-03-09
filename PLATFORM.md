# Platform and portability

GOAT-TS is written so the same code and workflow work on **Windows**, **macOS**, and **Linux**. This file explains what the repo relies on and how to verify or fix issues on a new system.

## What the code assumes (and why it works elsewhere)

| Concern | What we do | Why it works on other systems |
|--------|-------------|--------------------------------|
| **Paths** | `pathlib.Path(__file__).resolve().parents[1]` and `ROOT / "scripts" / "file.py"` everywhere | `Path` uses the OS separator. No hardcoded `\` or `/` for repo layout. |
| **Subprocess** | `subprocess.run([sys.executable, str(script_path), ...], cwd=str(ROOT))` — list args, no `shell=True` | Same Python, same CWD on every OS; no shell-specific parsing. |
| **Imports** | Scripts add `str(ROOT)` to `sys.path` or set `PYTHONPATH=str(ROOT)` when spawning children | Repo root is the package root on all platforms. |
| **Config files** | `Path(path).open()` and `configs/graph.yaml` via `ROOT / "configs" / "graph.yaml"` | Relative paths are resolved from repo root; YAML and encoding are portable. |
| **Docker** | `docker compose -f <path> up -d` with path from `Path.as_posix()` in the UI | Compose V2 and Docker CLI accept the same path form; script `start-local.sh` uses bash, `start-local.ps1` uses PowerShell. |
| **Line endings** | Repo should use LF in committed files; editors can handle CRLF on Windows | Avoids "no such file" when scripts are run on Unix. |

## Per-OS notes

- **Windows**
  - Use `python -m pytest` and `python scripts/apply_schema.py` (not `pytest` or `.\scripts\...` only) so behavior matches docs.
  - In PowerShell, chaining with `&&` fails; use `;` or run one command per line. README uses one command per block.
  - Venv: `.\.venv\Scripts\Activate.ps1`. Optional: `start-local.ps1` runs Docker via `cmd.exe` for compatibility.
- **macOS / Linux**
  - Venv: `source .venv/bin/activate`. Use `scripts/start-local.sh` to start Docker (or run `docker compose -f docker/docker-compose.yml up -d`).
  - Prefer `python3` in the venv if your system `python` is not 3.11+.

## How to confirm it works on your system

1. From repo root: `python scripts/apply_schema.py --dry-run` — should print schema steps and exit 0 (no Docker needed).
2. `python -m pytest tests/test_placeholder.py -v` — should pass (no Docker needed).
3. With Docker running: `docker compose -f docker/docker-compose.yml up -d`, then `python scripts/apply_schema.py --live` — should apply schema and exit 0.

If something fails, check: Python version (3.11+), current directory (repo root), and that no paths in the error message are hardcoded to another OS (e.g. `C:\` or `/home/someone` from a config on your machine).

## Optional: Git and line endings

To avoid CRLF/LF issues when collaborating across OSes:

```bash
git config core.autocrlf input
```

(On Windows you might use `true` instead of `input` so checked-out files use CRLF locally; the repo can still store LF.)
