"""
GOAT-TS Streamlit GUI — setup, config, ingestion, simulation, reasoning, monitoring, export & API.
Run from repo root: python -m streamlit run scripts/goat_ts_gui.py

Sidebar pages: Home, Setup Wizard, Config Editor, Data Ingestion, Simulation & Physics,
Reasoning Loop, Monitoring & Debug, Export & API. Use ?page=debug to open debug log in a new tab.
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

LOG_FILE = ROOT / ".goat_ts_gui_log.txt"
SUBPROCESS_TIMEOUT = 300
MAX_LOG_LINES = 500
DEBUG_DEFAULT_PORT = 8501


def _env() -> dict[str, str]:
    e = os.environ.copy()
    e["PYTHONPATH"] = str(ROOT)
    e["PYTHONIOENCODING"] = "utf-8"
    return e


def _append_log(line: str) -> None:
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def run_cmd(
    cmd: list[str],
    timeout: int = SUBPROCESS_TIMEOUT,
    cwd: Path | None = None,
) -> tuple[str, str, int]:
    """Run command; capture stdout/stderr; append to log file. Returns (stdout, stderr, returncode)."""
    cwd = cwd or ROOT
    _append_log(f">>> {' '.join(cmd)}")
    try:
        result = subprocess.run(
            cmd,
            cwd=str(cwd),
            env=_env(),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        out, err = result.stdout or "", result.stderr or ""
        for line in (out + err).splitlines():
            _append_log(line)
        _append_log(f"<<< exit {result.returncode}")
        return out, err, result.returncode
    except subprocess.TimeoutExpired:
        _append_log("<<< TIMEOUT")
        return "", "Command timed out.", -1
    except Exception as e:
        _append_log(f"<<< ERROR: {e}")
        return "", str(e), -1


def read_log_tail(n: int = MAX_LOG_LINES) -> str:
    """Read last n lines from log file."""
    if not LOG_FILE.exists():
        return "(No log output yet.)"
    try:
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()
        return "".join(lines[-n:])
    except Exception:
        return "(Could not read log.)"


def _check_system() -> None:
    """Run all setup checks and update session state: deps_ok, docker_ok, connect_ok, schema_applied."""
    # Step 1: dependencies (pip check)
    _, _, code = run_cmd([sys.executable, "-m", "pip", "check"], timeout=30)
    st.session_state.deps_ok = code == 0

    # Step 2: Docker
    compose = ROOT / "docker" / "docker-compose.yml"
    if compose.exists():
        out, err, code = run_cmd(
            ["docker", "compose", "-f", str(compose), "ps"],
            timeout=10,
        )
        st.session_state.docker_ok = code == 0 and "Up" in (out + err)
    else:
        st.session_state.docker_ok = False

    # Step 3 & 4: connection and schema (connect + SHOW SPACES)
    st.session_state.connect_ok = False
    try:
        import yaml
        graph_config = ROOT / "configs" / "graph.yaml"
        space_name = "ts_graph"
        if graph_config.exists():
            with open(graph_config, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            space_name = data.get("graph", {}).get("space", "ts_graph")
        from src.graph.client import NebulaGraphClient
        client = NebulaGraphClient(
            config_path=str(ROOT / "configs" / "graph.yaml"),
            dry_run_override=False,
        )
        try:
            result = client.query_ngql("SHOW SPACES;")
            ok = getattr(result, "is_succeeded", lambda: False)()
            if ok and hasattr(result, "row_size") and hasattr(result, "row_values"):
                for i in range(result.row_size()):
                    row = str(result.row_values(i))
                    if space_name in row:
                        st.session_state.schema_applied = True
                        break
            st.session_state.connect_ok = True
        finally:
            client.close()
    except Exception:
        st.session_state.connect_ok = False
        # Leave schema_applied unchanged if connect failed (might already be True from prior run)


def _run_wizard_task(cmd: list[str] | None, timeout: int, run_sync=None) -> None:
    """Run a wizard command in a background thread; store result in session_state. run_sync() for non-cmd tasks (e.g. test connection)."""
    result_holder = {"out": "", "err": "", "code": -1}

    def run() -> None:
        try:
            if cmd is not None:
                out, err, code = run_cmd(cmd, timeout=timeout)
                result_holder["out"], result_holder["err"], result_holder["code"] = out, err, code
            elif run_sync is not None:
                run_sync()
                result_holder["out"], result_holder["code"] = "Connected.", 0
        except Exception as e:
            result_holder["err"] = str(e)
            result_holder["code"] = -1
        finally:
            st.session_state.wizard_done = True
            st.session_state.wizard_result = (result_holder["out"], result_holder["err"], result_holder["code"])

    t = threading.Thread(target=run)
    t.daemon = True
    t.start()


def init_session_state() -> None:
    if "docker_ok" not in st.session_state:
        st.session_state.docker_ok = False
    if "schema_applied" not in st.session_state:
        st.session_state.schema_applied = False
    if "deps_ok" not in st.session_state:
        st.session_state.deps_ok = False
    if "connect_ok" not in st.session_state:
        st.session_state.connect_ok = False
    if "config_graph" not in st.session_state:
        st.session_state.config_graph = {}
    if "config_reasoning" not in st.session_state:
        st.session_state.config_reasoning = {}
    if "config_simulation" not in st.session_state:
        st.session_state.config_simulation = {}
    if "api_process" not in st.session_state:
        st.session_state.api_process = None
    if "wizard_last_duration" not in st.session_state:
        st.session_state.wizard_last_duration = {}
    # Stage 6: lightweight mode — no Docker/Spark required; all features use in-memory fallback
    if "lightweight_mode" not in st.session_state:
        st.session_state.lightweight_mode = False


try:
    import streamlit as st
except ImportError:
    print("Streamlit is required. Install with: pip install streamlit", file=sys.stderr)
    sys.exit(1)

init_session_state()

# Debug view: show only log when ?page=debug
try:
    if hasattr(st, "query_params"):
        page_param = st.query_params.get("page")
    else:
        q = getattr(st, "experimental_get_query_params", lambda: {})()
        page_param = (q.get("page") or [None])[0] if isinstance(q.get("page"), list) else q.get("page")
except Exception:
    page_param = None
if page_param == "debug":
    st.set_page_config(page_title="GOAT-TS Debug", layout="wide")
    st.title("Debug log")
    st.caption("Output from subprocess runs. Refresh to update.")
    if st.button("Refresh"):
        st.rerun()
    st.text_area("Log", value=read_log_tail(2000), height=600, disabled=True)
    st.stop()

# Main app
st.set_page_config(page_title="GOAT-TS", layout="wide", initial_sidebar_state="expanded")

PAGES = [
    "Home",
    "Setup Wizard",
    "Config Editor",
    "Data Ingestion",
    "Simulation & Physics",
    "Reasoning Loop",
    "Monitoring & Debug",
    "Export & API",
]

page = st.sidebar.radio("Navigate", PAGES, index=0)
st.sidebar.caption("---")
st.sidebar.caption("**Status**")
st.sidebar.caption(f"Deps: {'✓' if st.session_state.deps_ok else '—'}")
st.sidebar.caption(f"Docker: {'✓' if st.session_state.docker_ok else '—'}")
st.sidebar.caption(f"Connect: {'✓' if st.session_state.connect_ok else '—'}")
st.sidebar.caption(f"Schema: {'✓' if st.session_state.schema_applied else '—'}")
st.sidebar.caption(f"Lightweight: {'✓' if st.session_state.get('lightweight_mode') else '—'}")

# ---------- Home ----------
if page == "Home":
    st.title("GOAT-TS")
    st.markdown("Local-first scaffold for a **knowledge-graph–driven cognition** architecture: ingest text, run spreading activation and memory, then reason over tension and hypotheses.")
    st.info("**Get started:** Go to **Setup Wizard** in the sidebar and complete the steps (dependencies → Docker → schema).")
    st.subheader("Docs")
    c1, c2, c3 = st.columns(3)
    with c1:
        if (ROOT / "README.md").exists():
            st.markdown("[README.md](README.md)")
    with c2:
        if (ROOT / "ROADMAP.md").exists():
            st.markdown("[ROADMAP.md](ROADMAP.md)")
    with c3:
        if (ROOT / "CONTRIBUTING.md").exists():
            st.markdown("[CONTRIBUTING.md](CONTRIBUTING.md)")
    st.caption("Run all commands from repo root. See PLATFORM.md for Windows/macOS/Linux notes.")

# ---------- Setup Wizard ----------
elif page == "Setup Wizard":
    st.title("Setup Wizard")
    lightweight = st.checkbox(
        "Lightweight mode (no Docker/Spark — all features use in-memory fallback)",
        value=st.session_state.get("lightweight_mode", False),
        key="lightweight_checkbox",
    )
    st.session_state.lightweight_mode = lightweight
    if lightweight:
        st.info("Lightweight mode is on. Demos and reasoning use dry-run; Docker/Spark steps are optional.")
    steps_done = (
        (1 if st.session_state.deps_ok else 0)
        + (1 if st.session_state.docker_ok else 0)
        + (1 if st.session_state.connect_ok else 0)
        + (1 if st.session_state.schema_applied else 0)
    )
    st.progress(min(1.0, steps_done / 4), text=f"Completed: {steps_done} of 4")
    if st.button("Check system (verify all steps)", type="primary"):
        with st.spinner("Checking dependencies, Docker, connection, schema…"):
            _check_system()
        st.rerun()
    st.caption("Run this first to see what’s already done; completed steps are then locked.")

    # Live progress: when a wizard task is running, show elapsed time and progress bar (fragment reruns every 1s)
    wizard_task = st.session_state.get("wizard_task")
    wizard_done = st.session_state.get("wizard_done")
    wizard_start = st.session_state.get("wizard_start")
    wizard_estimated = st.session_state.get("wizard_estimated", 60)

    if wizard_task and wizard_start is not None:
        try:
            @st.fragment(run_every=1)
            def wizard_live_progress():
                if st.session_state.get("wizard_done"):
                    out, err, code = st.session_state.get("wizard_result") or ("", "", -1)
                    task = st.session_state.get("wizard_task")
                    elapsed = time.time() - st.session_state.wizard_start
                    st.success(f"Completed in {elapsed:.1f} s")
                    if code == 0:
                        st.success("Task finished successfully.")
                        # Persist last run duration for dynamic estimates
                        if "wizard_last_duration" not in st.session_state:
                            st.session_state.wizard_last_duration = {}
                        st.session_state.wizard_last_duration[task] = round(elapsed, 1)
                        if task == "install":
                            st.session_state.deps_ok = True
                        if task == "docker_up":
                            st.session_state.docker_ok = True
                        if task == "docker_ps":
                            st.session_state.docker_ok = "Up" in (out + err)
                        if task == "connect":
                            st.session_state.connect_ok = True
                        if task == "schema_live":
                            st.session_state.schema_applied = True
                    else:
                        st.error(err or out or "Task failed.")
                        if task == "docker_ps":
                            st.session_state.docker_ok = False
                        if task == "install" and ("timed out" in (err or "").lower() or "cancelled" in (err or "").lower() or code == -1):
                            st.info("If install timed out or was cancelled, run in a terminal: **python -m pip install -r requirements.txt** (from repo root). Then return to the wizard.")
                    st.text_area("Output", value=(out + "\n" + err).strip() or "(no output)", height=140, disabled=True, key="wizard_result_area")
                    st.session_state.wizard_task = None
                    st.session_state.wizard_done = False
                    st.session_state.wizard_result = None
                    st.session_state.wizard_start = None
                    return
                elapsed = time.time() - st.session_state.wizard_start
                est = st.session_state.get("wizard_estimated") or 60
                progress_val = min(0.95, elapsed / est) if est > 0 else 0.5
                st.progress(progress_val, text=f"Running… {elapsed:.0f} s elapsed (est. {est} s)")
                st.metric("Elapsed", f"{elapsed:.1f} s")
                st.caption(f"Estimated duration: {est} s — updates every second.")
            wizard_live_progress()
        except Exception:
            # Fallback if st.fragment(run_every=...) not available
            if wizard_done:
                out, err, code = st.session_state.get("wizard_result") or ("", "", -1)
                elapsed = time.time() - wizard_start
                st.success(f"Completed in {elapsed:.1f} s")
                st.text_area("Output", value=out + "\n" + err, height=140, disabled=True, key="wizard_result_fb")
                st.session_state.wizard_task = None
                st.session_state.wizard_done = False
                st.session_state.wizard_result = None

    # Step 1 — Dependencies (estimate from last run or default)
    _last = st.session_state.get("wizard_last_duration") or {}
    EST_INSTALL_DEFAULT = 300
    est_install = _last.get("install", EST_INSTALL_DEFAULT)
    INSTALL_TIMEOUT = 900
    with st.expander("Step 1 — Dependencies", expanded=True):
        est_cap = f"**Time estimate:** {est_install:.0f} s" + (f" (last run: {est_install:.0f} s)" if "install" in _last else " (typical 2–5 min).") + f" Allowed up to {INSTALL_TIMEOUT // 60} min."
        st.caption(r"Python 3.11+. Install requirements. On Windows use `;` not `&&`; venv: `.\.venv\Scripts\Activate.ps1`.")
        st.caption(est_cap)
        py_ver = sys.version_info
        if py_ver >= (3, 11):
            st.success(f"Python {py_ver.major}.{py_ver.minor}.{py_ver.micro} ✓")
        else:
            st.warning(f"Python {py_ver.major}.{py_ver.minor} — 3.11+ recommended.")
        step1_done = st.session_state.deps_ok
        if step1_done:
            st.success("Dependencies OK (already verified or installed).")
        if st.button("Install dependencies (pip install -r requirements.txt)", disabled=step1_done):
            st.session_state.wizard_task = "install"
            st.session_state.wizard_start = time.time()
            st.session_state.wizard_estimated = int(est_install)
            st.session_state.wizard_done = False
            st.session_state.wizard_result = None
            _run_wizard_task(
                [sys.executable, "-m", "pip", "install", "-r", "requirements.txt"],
                timeout=INSTALL_TIMEOUT,
            )
            st.rerun()

    # Step 2 — Docker (estimates from last run or default)
    est_docker_up = _last.get("docker_up", 60)
    est_docker_ps = _last.get("docker_ps", 5)
    with st.expander("Step 2 — Docker", expanded=True):
        st.caption("Start NebulaGraph, Redis, Spark via Docker Compose.")
        st.caption(f"**Time estimates:** Start {est_docker_up:.0f} s; Check {est_docker_ps:.0f} s" + (" (from last run)" if "docker_up" in _last or "docker_ps" in _last else " (typical 30–90 s / 5 s)."))
        step2_done = st.session_state.docker_ok
        if step2_done:
            st.success("Docker is up.")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Start Docker", disabled=step2_done):
                compose = ROOT / "docker" / "docker-compose.yml"
                if not compose.exists():
                    st.error("docker/docker-compose.yml not found.")
                else:
                    st.session_state.wizard_task = "docker_up"
                    st.session_state.wizard_start = time.time()
                    st.session_state.wizard_estimated = int(est_docker_up)
                    st.session_state.wizard_done = False
                    st.session_state.wizard_result = None
                    _run_wizard_task(
                        ["docker", "compose", "-f", str(compose), "up", "-d"],
                        timeout=120,
                    )
                    st.rerun()
        with col2:
            if st.button("Check Docker status"):
                compose = ROOT / "docker" / "docker-compose.yml"
                if not compose.exists():
                    st.error("docker/docker-compose.yml not found.")
                else:
                    st.session_state.wizard_task = "docker_ps"
                    st.session_state.wizard_start = time.time()
                    st.session_state.wizard_estimated = int(est_docker_ps)
                    st.session_state.wizard_done = False
                    st.session_state.wizard_result = None
                    _run_wizard_task(
                        ["docker", "compose", "-f", str(compose), "ps"],
                        timeout=10,
                    )
                    st.rerun()

    # Step 3 — Connect (est. 2–5 s)
    EST_CONNECT = 5
    with st.expander("Step 3 — Connect"):
        st.caption("NebulaGraph and Redis. Credentials in configs/graph.yaml and .env (see README).")
        st.caption("**Time estimate:** ~2–5 s.")
        if st.button("Test connection (live)"):
            def _test_connect():
                from src.graph.client import NebulaGraphClient
                client = NebulaGraphClient(config_path=str(ROOT / "configs" / "graph.yaml"), dry_run_override=False)
                client.close()
            st.session_state.wizard_task = "connect"
            st.session_state.wizard_start = time.time()
            st.session_state.wizard_estimated = EST_CONNECT
            st.session_state.wizard_done = False
            st.session_state.wizard_result = None
            _run_wizard_task(None, EST_CONNECT, run_sync=_test_connect)
            st.rerun()

    # Step 4 — Schema (estimates from last run or default)
    est_schema_dry = _last.get("schema_dry", 5)
    est_schema_live = _last.get("schema_live", 30)
    with st.expander("Step 4 — Schema", expanded=True):
        st.caption("Apply NebulaGraph schema. Dry-run first, then live after Docker is up.")
        st.caption(f"**Time estimates:** Dry-run {est_schema_dry:.0f} s; Live {est_schema_live:.0f} s" + (" (from last run)" if "schema_dry" in _last or "schema_live" in _last else " (typical 5 s / 15–30 s)."))
        step4_done = st.session_state.schema_applied
        if step4_done:
            st.success("Schema applied.")
        live_ok = st.session_state.docker_ok
        if not live_ok:
            st.warning("Start Docker and run Check status before applying live.")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Apply schema (dry-run)"):
                st.session_state.wizard_task = "schema_dry"
                st.session_state.wizard_start = time.time()
                st.session_state.wizard_estimated = int(est_schema_dry)
                st.session_state.wizard_done = False
                st.session_state.wizard_result = None
                _run_wizard_task(
                    [sys.executable, "scripts/apply_schema.py", "--dry-run"],
                    timeout=30,
                )
                st.rerun()
        with col2:
            if st.button("Apply schema (live)", disabled=(not live_ok or step4_done)):
                st.session_state.wizard_task = "schema_live"
                st.session_state.wizard_start = time.time()
                st.session_state.wizard_estimated = int(est_schema_live)
                st.session_state.wizard_done = False
                st.session_state.wizard_result = None
                _run_wizard_task(
                    [sys.executable, "scripts/apply_schema.py", "--live"],
                    timeout=60,
                )
                st.rerun()

    st.caption("Next: Config Editor or Data Ingestion.")

# ---------- Config Editor ----------
elif page == "Config Editor":
    st.title("Config Editor")
    st.caption("Load, edit, validate, and save YAML configs. Keys match configs/*.yaml.")

    config_file = st.selectbox("Config file", ["configs/graph.yaml", "configs/reasoning.yaml", "configs/simulation.yaml"])
    path = ROOT / config_file
    if not path.exists():
        st.warning(f"File not found: {path}")

    if st.button("Load from file"):
        try:
            import yaml
            with open(path, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            st.session_state.config_raw[config_file] = data
            if "graph" in data:
                st.session_state.config_graph = data.get("graph", {})
            if "reasoning" in data:
                st.session_state.config_reasoning = data.get("reasoning", {})
            if "simulation" in data:
                st.session_state.config_simulation = data.get("simulation", {})
            st.success("Loaded.")
        except Exception as e:
            st.error(str(e))

    if "graph.yaml" in config_file:
        st.subheader("Graph")
        g = st.session_state.config_graph or {}
        with st.form("graph_form"):
            host = st.text_input("host", value=g.get("host", "127.0.0.1"))
            port = st.number_input("port", value=int(g.get("port", 9669)), min_value=1)
            username = st.text_input("username", value=g.get("username", "root"))
            password = st.text_input("password", value=g.get("password", "nebula"), type="password")
            space = st.text_input("space", value=g.get("space", "ts_graph"))
            dry_run = st.checkbox("dry_run", value=g.get("dry_run", True))
            if st.form_submit_button("Save"):
                try:
                    import yaml
                    full = {**({"graph": dict(st.session_state.config_graph)} if st.session_state.config_graph else {})}
                    full.setdefault("graph", {})["host"] = host
                    full["graph"]["port"] = port
                    full["graph"]["username"] = username
                    full["graph"]["password"] = password
                    full["graph"]["space"] = space
                    full["graph"]["dry_run"] = dry_run
                    with open(path, "w", encoding="utf-8") as f:
                        yaml.dump(full, f, default_flow_style=False, sort_keys=False)
                    st.success("Saved.")
                except Exception as e:
                    st.error(str(e))

    elif "reasoning.yaml" in config_file:
        st.subheader("Reasoning")
        r = st.session_state.config_reasoning or {}
        with st.form("reasoning_form"):
            cache_enabled = st.checkbox("cache_enabled", value=r.get("cache_enabled", False))
            cache_ttl_s = st.number_input("cache_ttl_s", value=int(r.get("cache_ttl_s", 300)))
            node_limit = st.number_input("node_limit", value=int(r.get("node_limit", 200)))
            edge_limit = st.number_input("edge_limit", value=int(r.get("edge_limit", 1000)))
            if st.form_submit_button("Save"):
                try:
                    import yaml
                    full = dict(st.session_state.config_raw.get(config_file, {}))
                    r2 = {**r, "cache_enabled": cache_enabled, "cache_ttl_s": cache_ttl_s, "node_limit": node_limit, "edge_limit": edge_limit}
                    full["reasoning"] = r2
                    st.session_state.config_reasoning = r2
                    with open(path, "w", encoding="utf-8") as f:
                        yaml.dump(full, f, default_flow_style=False, sort_keys=False)
                    st.success("Saved.")
                except Exception as e:
                    st.error(str(e))

    elif "simulation.yaml" in config_file:
        st.subheader("Simulation")
        s = st.session_state.config_simulation or {}
        with st.form("simulation_form"):
            use_gpu = st.checkbox("use_gpu", value=s.get("use_gpu", False))
            gravitational_constant = st.number_input("gravitational_constant", value=float(s.get("gravitational_constant", 0.1)), format="%.2f")
            damping = st.number_input("damping", value=float(s.get("damping", 0.02)), format="%.2f")
            if st.form_submit_button("Save"):
                try:
                    import yaml
                    full = {"simulation": {**s, "use_gpu": use_gpu, "gravitational_constant": gravitational_constant, "damping": damping}}
                    with open(path, "w", encoding="utf-8") as f:
                        yaml.dump(full, f, default_flow_style=False, sort_keys=False)
                    st.session_state.config_simulation = full["simulation"]
                    st.success("Saved.")
                except Exception as e:
                    st.error(str(e))

# ---------- Data Ingestion ----------
elif page == "Data Ingestion":
    st.title("Data Ingestion")
    with st.expander("Acquire dumps", expanded=True):
        st.caption("Download or generate corpus text (sample, wikipedia-api, wikipedia-sample).")
        source = st.selectbox("Source", ["sample", "wikipedia-api", "wikipedia-sample"])
        max_docs = st.number_input("Max docs", value=200, min_value=1)
        output_dir = st.text_input("Output dir", value="data/raw")
        if st.button("Run acquire"):
            out, err, code = run_cmd([
                sys.executable, "scripts/acquire_dumps.py",
                "--source", source, "--max-docs", str(max_docs), "--output-dir", output_dir,
            ], timeout=120)
            if code == 0:
                st.success("Done.")
            else:
                st.error(err or out)
            st.text_area("Output", value=out + "\n" + err, height=150, disabled=True, key="acquire_out")

    with st.expander("Spark ETL"):
        st.caption("Requires JAVA_HOME. Reads text, writes Parquet.")
        input_path = st.text_input("Input path", value="data/raw/wikipedia/abstracts.txt")
        output_path = st.text_input("Output path", value="data/processed/corpus.parquet")
        if st.button("Run Spark ETL"):
            inp = str(ROOT / input_path) if not Path(input_path).is_absolute() else input_path
            out_path = str(ROOT / output_path) if not Path(output_path).is_absolute() else output_path
            out, err, code = run_cmd([
                sys.executable, "scripts/run_spark_etl.py",
                "--input-path", inp, "--output-path", out_path,
            ], timeout=300)
            if code == 0:
                st.success("Done.")
            else:
                st.error(err or out)
            st.text_area("Output", value=out + "\n" + err, height=150, disabled=True, key="spark_out")

    with st.expander("Extraction pipeline"):
        st.caption("Extract triples and load into graph. Use --live after schema applied.")
        input_path = st.text_input("Extraction input path", value="data/raw/wikipedia/abstracts.txt", key="ext_inp")
        use_live = st.checkbox("--live", value=False)
        global_merge = st.checkbox("--global-merge", value=False)
        merge_threshold = st.number_input("--merge-threshold", value=0.8, format="%.2f")
        if st.button("Run extraction (dry-run)"):
            cmd = [sys.executable, "-m", "src.ingestion.extraction_pipeline", "--input-path", str(ROOT / input_path)]
            if global_merge:
                cmd += ["--global-merge", "--merge-threshold", str(merge_threshold)]
            out, err, code = run_cmd(cmd, timeout=600)
            if code == 0:
                st.success("Done.")
            else:
                st.error(err or out)
            st.text_area("Output", value=out + "\n" + err, height=180, disabled=True, key="ext_dry")
        if st.button("Run extraction (live)"):
            cmd = [sys.executable, "-m", "src.ingestion.extraction_pipeline", "--input-path", str(ROOT / input_path), "--live"]
            if global_merge:
                cmd += ["--global-merge", "--merge-threshold", str(merge_threshold)]
            out, err, code = run_cmd(cmd, timeout=600)
            if code == 0:
                st.success("Done.")
            else:
                st.error(err or out)
            st.text_area("Output", value=out + "\n" + err, height=180, disabled=True, key="ext_live")

# ---------- Simulation & Physics ----------
elif page == "Simulation & Physics":
    st.title("Simulation & Physics")
    with st.expander("Generate sample graph", expanded=True):
        st.caption("Create synthetic nodes/edges; optionally write to live graph.")
        node_count = st.number_input("Node count", value=1000, min_value=10)
        edge_count = st.number_input("Edge count", value=2500, min_value=10)
        use_live = st.checkbox("--live", value=False)
        if st.button("Generate sample graph"):
            cmd = [sys.executable, "scripts/generate_sample_100k.py", "--node-count", str(node_count), "--edge-count", str(edge_count)]
            if use_live:
                cmd.append("--live")
            out, err, code = run_cmd(cmd, timeout=120)
            if code == 0:
                st.success("Done.")
            else:
                st.error(err or out)
            st.text_area("Output", value=out + "\n" + err, height=120, disabled=True, key="gen_out")

    with st.expander("Gravity demo"):
        st.caption("Run gravity simulation (run_gravity_demo.py).")
        iterations = st.number_input("Iterations", value=100, min_value=1)
        use_live = st.checkbox("Live graph", value=False, key="grav_live")
        output_path = st.text_input("Output JSON", value="examples/gravity_out.json")
        plot_path = st.text_input("Plot PNG", value="examples/gravity_plot.png")
        if st.button("Run gravity demo"):
            cmd = [sys.executable, "scripts/run_gravity_demo.py", "--iterations", str(iterations)]
            if use_live:
                cmd.append("--live")
            if output_path:
                cmd += ["--output", str(ROOT / output_path)]
            if plot_path:
                cmd += ["--plot", str(ROOT / plot_path)]
            out, err, code = run_cmd(cmd, timeout=180)
            if code == 0:
                st.success("Done.")
            else:
                st.error(err or out)
            st.text_area("Output", value=out + "\n" + err, height=120, disabled=True, key="grav_out")

    with st.expander("Cognition demo loop"):
        st.caption("Spreading activation + memory tick + optional gravity (demo_loop).")
        seed_labels = st.text_input("Seed labels", value="concept")
        ticks = st.number_input("Ticks", value=10, min_value=1)
        decay_rate = st.number_input("Decay rate", value=0.95, format="%.2f")
        enable_forces = st.checkbox("Enable forces", value=False)
        export_dot = st.text_input("Export .dot path", value="")
        if st.button("Run demo loop"):
            cmd = [
                sys.executable, "-m", "src.agi_loop.demo_loop",
                "--dry-run", "--seed-labels", seed_labels, "--ticks", str(ticks),
                "--decay-rate", str(decay_rate), "--config", "configs/graph.yaml",
            ]
            if enable_forces:
                cmd.append("--enable-forces")
            if export_dot:
                cmd += ["--export-dot", str(ROOT / export_dot)]
            with st.spinner("Running..."):
                out, err, code = run_cmd(cmd, timeout=120)
            if code == 0:
                st.success("Done.")
            else:
                st.error(err or out)
            st.text_area("Output", value=out + "\n" + err, height=200, disabled=True, key="demo_out")

# ---------- Reasoning Loop ----------
elif page == "Reasoning Loop":
    st.title("Reasoning Loop")
    with st.expander("Demo loop (with Step 7 options)", expanded=True):
        st.caption("Full demo_loop: seeds, ticks, forces, self-reflection, curiosity, compression.")
        seed_labels = st.text_input("Seed labels", value="concept", key="rl_seed")
        ticks = st.number_input("Ticks", value=5, min_value=1, key="rl_ticks")
        enable_forces = st.checkbox("Enable forces", value=False, key="rl_forces")
        enable_self_reflection = st.checkbox("Enable self-reflection", value=False)
        enable_goal_generator = st.checkbox("Enable goal generator", value=False)
        enable_curiosity = st.checkbox("Enable curiosity", value=False)
        enable_compression = st.checkbox("Enable compression", value=False)
        compression_archive = st.text_input("Compression archive path", value="", key="comp_arch")
        if st.button("Run demo loop"):
            cmd = [
                sys.executable, "-m", "src.agi_loop.demo_loop",
                "--dry-run", "--seed-labels", seed_labels, "--ticks", str(ticks),
                "--config", "configs/graph.yaml",
            ]
            if enable_forces:
                cmd.append("--enable-forces")
            if enable_self_reflection:
                cmd.append("--enable-self-reflection")
            if enable_goal_generator:
                cmd.append("--enable-goal-generator")
            if enable_curiosity:
                cmd.append("--enable-curiosity")
            if enable_compression:
                cmd.append("--enable-compression")
                if compression_archive:
                    cmd += ["--compression-archive", str(ROOT / compression_archive)]
            with st.spinner("Running..."):
                out, err, code = run_cmd(cmd, timeout=120)
            if code == 0:
                st.success("Done.")
            else:
                st.error(err or out)
            st.text_area("Output", value=out + "\n" + err, height=220, disabled=True, key="rloop_out")

    with st.expander("Reasoning demo (query → hypotheses)"):
        st.caption("Run reasoning loop: query string → activated nodes, tension, hypotheses.")
        query = st.text_input("Query", value="Wikipedia supports free knowledge and Wikidata supports structured facts.", key="reason_query")
        use_live = st.checkbox("--live", value=False, key="reason_live")
        if st.button("Run reasoning"):
            cmd = [sys.executable, "scripts/run_reasoning_demo.py", "--query", query]
            if use_live:
                cmd.append("--live")
            out, err, code = run_cmd(cmd, timeout=60)
            if code == 0:
                st.success("Done.")
            else:
                st.error(err or out)
            st.text_area("Output", value=out + "\n" + err, height=200, disabled=True, key="reason_out")

# ---------- Monitoring & Debug ----------
elif page == "Monitoring & Debug":
    st.title("Monitoring & Debug")
    st.caption("Graph stats, log viewer, and debug window (open in new tab).")

    if st.button("Dump graph stats (live)"):
        out, err, code = run_cmd([sys.executable, "scripts/dump_graph_stats.py", "--live"], timeout=30)
        st.text_area("Stats", value=out + "\n" + err, height=150, disabled=True, key="stats_live")
    if st.button("Dump graph stats (dry-run)"):
        out, err, code = run_cmd([sys.executable, "scripts/dump_graph_stats.py"], timeout=30)
        st.text_area("Stats", value=out + "\n" + err, height=150, disabled=True, key="stats_dry")

    st.subheader("Log output")
    if st.button("Clear log"):
        try:
            if LOG_FILE.exists():
                LOG_FILE.write_text("")
            st.rerun()
        except Exception:
            pass
    st.text_area("Last output", value=read_log_tail(), height=300, disabled=True, key="monitor_log")

    st.subheader("Debug window")
    st.caption("Open this app in a new tab with ?page=debug to see the full log. Default port 8501:")
    st.code("http://localhost:8501/?page=debug", language=None)
    st.markdown("[Open Debug Window (right-click → Open link in new tab)](/?page=debug)")

    with st.expander("Metrics (stub)"):
        st.caption("Prometheus metrics are available at /metrics when the API server is running.")
        st.caption("See src/monitoring/metrics.py and docker/docker-compose.yml for Prometheus/Grafana stubs.")

    with st.expander("Provenance tracing (concept → waves)"):
        st.caption("Inspect which cognition waves contributed to a concept (requires live NebulaGraph).")
        concept_label = st.text_input("Concept label contains", value="", key="prov_label")
        if st.button("Trace provenance"):
            if not concept_label.strip():
                st.warning("Enter a label substring to search for concept nodes.")
            else:
                try:
                    from src.graph.client import NebulaGraphClient

                    client = NebulaGraphClient(config_path=str(ROOT / "configs" / "graph.yaml"), dry_run_override=False)
                    try:
                        nodes = client.list_nodes_by_label_keywords([concept_label], limit=20)
                        if not nodes:
                            st.info("No matching concept nodes found.")
                        else:
                            target_ids = {n.node_id for n in nodes}
                            in_wave_edges = client.list_in_wave_edges(limit=5000)
                            wave_ids = {e.dst_id for e in in_wave_edges if e.src_id in target_ids}
                            if not wave_ids:
                                st.info("No in_wave provenance edges found for matching concepts.")
                            else:
                                waves = [w for w in client.list_waves(limit=500) if w.wave_id in wave_ids]
                                st.write("Matching concepts")
                                st.table([{"node_id": n.node_id, "label": n.label, "activation": round(n.activation, 3)} for n in nodes])
                                st.write("Provenance waves")
                                st.table(
                                    [
                                        {
                                            "wave_id": w.wave_id,
                                            "label": w.label,
                                            "source": w.source,
                                            "tension": round(w.tension, 4),
                                        }
                                        for w in waves
                                    ]
                                )
                    finally:
                        client.close()
                except Exception as e:
                    st.error(str(e))

# ---------- Export & API ----------
elif page == "Export & API":
    st.title("Export & API")
    with st.expander("Export subgraph", expanded=True):
        st.caption("Export subgraph to JSON, PNG, or Graphviz .dot (export_subgraph.py).")
        concept = st.text_input("Concept (--concept)", value="Concept 1")
        hops = st.number_input("Hops", value=1, min_value=1)
        output_json = st.text_input("Output JSON", value="examples/export_out.json")
        output_plot = st.text_input("Plot PNG", value="")
        output_dot = st.text_input("Output .dot", value="")
        use_live = st.checkbox("--live", value=False, key="exp_live")
        if st.button("Export JSON"):
            cmd = [sys.executable, "scripts/export_subgraph.py", "--concept", concept, "--hops", str(hops), "--output", str(ROOT / output_json)]
            if use_live:
                cmd.append("--live")
            out, err, code = run_cmd(cmd, timeout=30)
            if code == 0:
                st.success(f"Wrote to {output_json}")
            else:
                st.error(err or out)
            st.text_area("Output", value=out + "\n" + err, height=80, disabled=True, key="exp_json")
        if output_plot and st.button("Export with PNG"):
            cmd = [sys.executable, "scripts/export_subgraph.py", "--concept", concept, "--output", str(ROOT / output_json), "--plot", str(ROOT / output_plot)]
            if use_live:
                cmd.append("--live")
            out, err, code = run_cmd(cmd, timeout=30)
            if code == 0:
                st.success("Done.")
            else:
                st.error(err or out)
            st.text_area("Output", value=out + "\n" + err, height=80, disabled=True, key="exp_png")
        if output_dot and st.button("Export DOT"):
            cmd = [sys.executable, "scripts/export_subgraph.py", "--concept", concept, "--output", str(ROOT / output_json), "--dot", str(ROOT / output_dot)]
            if use_live:
                cmd.append("--live")
            out, err, code = run_cmd(cmd, timeout=30)
            if code == 0:
                st.success("Done.")
            else:
                st.error(err or out)
            st.text_area("Output", value=out + "\n" + err, height=80, disabled=True, key="exp_dot")

    with st.expander("API server"):
        st.caption("Start/stop FastAPI server (serve_api.py). Test endpoints.")
        if st.session_state.api_process is None:
            if st.button("Start API server"):
                try:
                    st.session_state.api_process = subprocess.Popen(
                        [sys.executable, "-m", "uvicorn", "scripts.serve_api:app", "--host", "0.0.0.0", "--port", "8000"],
                        cwd=str(ROOT),
                        env={**os.environ, "PYTHONPATH": str(ROOT)},
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                    )
                    st.success("Server starting at http://localhost:8000")
                    st.rerun()
                except Exception as e:
                    st.error(str(e))
        else:
            st.success("Server running at http://localhost:8000")
            if st.button("Stop API server"):
                try:
                    st.session_state.api_process.terminate()
                    st.session_state.api_process.wait(timeout=5)
                except Exception:
                    pass
                st.session_state.api_process = None
                st.rerun()

    with st.expander("Test endpoints"):
        st.caption("Call API (requires server running).")
        if st.button("GET /health"):
            try:
                import urllib.request
                with urllib.request.urlopen("http://localhost:8000/health", timeout=5) as r:
                    body = r.read().decode()
                st.json(body if body.startswith("{") else {"raw": body})
            except Exception as e:
                st.error(str(e))
        if st.button("POST /run_demo (example)"):
            try:
                import urllib.request
                import json
                data = json.dumps({"ticks": 3, "dry_run": True, "seed_labels": "concept"}).encode()
                req = urllib.request.Request("http://localhost:8000/run_demo", data=data, method="POST", headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=30) as r:
                    body = r.read().decode()
                st.json(json.loads(body))
            except Exception as e:
                st.error(str(e))
