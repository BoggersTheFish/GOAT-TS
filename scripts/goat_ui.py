"""
GOAT Engine UI – one step at a time. Only the current step has an active button;
completing it unlocks the next. Debug report always available for copy-paste.
Run:  python scripts/goat_ui.py   (from repo root)
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path
from queue import Queue

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

ENV = os.environ.copy()
ENV["PYTHONPATH"] = str(ROOT)
ENV["PYTHONIOENCODING"] = "utf-8"


def _run(cmd: list[str], cwd: Path | None = None, timeout: int = 120) -> tuple[int, str, str]:
    try:
        r = subprocess.run(
            cmd,
            cwd=cwd or ROOT,
            env=ENV,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        return r.returncode, (r.stdout or "").strip(), (r.stderr or "").strip()
    except subprocess.TimeoutExpired:
        return -1, "", "Timeout"
    except Exception as e:
        return -1, "", str(e)


def check_docker() -> tuple[bool, str]:
    code, out, err = _run(["docker", "info"], timeout=10)
    return (code == 0, "Docker is running." if code == 0 else (err or out or "Docker not found or not running."))


def check_schema_applied() -> tuple[bool, str]:
    """Can we connect to Nebula and run a query (space exists and is usable)?"""
    try:
        from src.graph.client import NebulaGraphClient
        client = NebulaGraphClient(ROOT / "configs" / "graph.yaml", dry_run_override=False)
        try:
            client.list_nodes(limit=1)
            return True, "Schema/space exists and is usable."
        finally:
            client.close()
    except Exception as e:
        return False, str(e)[:200]


def check_graph_has_data() -> tuple[bool, str]:
    try:
        from src.graph.client import NebulaGraphClient
        client = NebulaGraphClient(ROOT / "configs" / "graph.yaml", dry_run_override=False)
        try:
            nodes = client.list_nodes(limit=1)
            client.close()
            return (len(nodes) > 0, f"Graph has data ({len(nodes)} node(s) sampled)." if nodes else "Graph is empty.")
        except Exception as e:
            try:
                client.close()
            except Exception:
                pass
            return False, str(e)[:200]
    except Exception as e:
        return False, str(e)[:200]


def run_apply_schema() -> tuple[bool, str]:
    code, out, err = _run([sys.executable, str(ROOT / "scripts" / "apply_schema.py"), "--live"], timeout=45)
    msg = out + ("\n" + err if err else "")
    return code == 0, msg or f"Exit code {code}"


def run_generate_sample() -> tuple[bool, str]:
    code, out, err = _run([
        sys.executable, str(ROOT / "scripts" / "generate_sample_100k.py"),
        "--node-count", "3000", "--edge-count", "8000", "--live",
    ], timeout=90)
    msg = out + ("\n" + err if err else "")
    return code == 0, msg or f"Exit code {code}"


def run_acquire_dumps() -> tuple[bool, str]:
    (ROOT / "data" / "raw").mkdir(parents=True, exist_ok=True)
    code, out, err = _run([
        sys.executable, str(ROOT / "scripts" / "acquire_dumps.py"),
        "--output-dir", str(ROOT / "data" / "raw"), "--max-docs", "150",
    ], timeout=300)
    msg = out + ("\n" + err if err else "")
    return code == 0, msg or f"Exit code {code}"


def run_extraction_pipeline() -> tuple[bool, str]:
    inp = ROOT / "data" / "raw" / "wikipedia" / "abstracts.txt"
    if not inp.exists():
        return False, f"Missing {inp}. Run 'Acquire dumps' first."
    code, out, err = _run([
        sys.executable, "-m", "src.ingestion.extraction_pipeline",
        "--input-path", str(inp), "--live",
    ], timeout=600)
    msg = out + ("\n" + err if err else "")
    return code == 0, msg or f"Exit code {code}"


def run_simulation() -> tuple[bool, str]:
    code, out, err = _run([
        sys.executable, str(ROOT / "scripts" / "run_simulation.py"), "--live", "--edge-limit", "500",
    ], timeout=60)
    msg = out + ("\n" + err if err else "")
    return code == 0, msg or f"Exit code {code}"


def run_reasoning(query: str) -> tuple[bool, str]:
    if not query.strip():
        return False, "Enter a query."
    code, out, err = _run([
        sys.executable, str(ROOT / "scripts" / "run_reasoning_demo.py"), "--live", "--query", query.strip(),
    ], timeout=60)
    msg = out + ("\n" + err if err else "")
    return code == 0, msg or f"Exit code {code}"


def get_debug_report() -> str:
    lines = [
        "--- GOAT Debug Report ---",
        f"Generated: {datetime.utcnow().isoformat()}Z",
        f"Repo root: {ROOT}",
        f"Python: {sys.executable}",
        f"Python version: {sys.version}",
        f"VIRTUAL_ENV: {os.environ.get('VIRTUAL_ENV', '(none)')}",
        "",
    ]
    ok, msg = check_docker()
    lines.append(f"Docker: {'OK' if ok else 'FAIL'} - {msg}")
    ok, msg = check_schema_applied()
    lines.append(f"Schema: {'OK' if ok else 'FAIL'} - {msg}")
    ok, msg = check_graph_has_data()
    lines.append(f"Graph data: {'OK' if ok else 'FAIL'} - {msg}")
    lines.append("--- End report ---")
    return "\n".join(lines)


def main() -> None:
    try:
        import tkinter as tk
        from tkinter import ttk, scrolledtext, messagebox
    except ImportError:
        print("tkinter is required.")
        sys.exit(1)

    root = tk.Tk()
    root.title("GOAT Engine")
    root.minsize(480, 420)
    root.geometry("560x480")

    # State: which step we're on (1..6). Step 0 = Docker, 1 = Schema, 2 = Data, 3 = Simulation, 4 = Reasoning, 5 = Debug always
    step_done = [False, False, False, False, False]  # Docker, Schema, Data, Sim, Reasoning
    current_step = 0

    main_f = ttk.Frame(root, padding=12)
    main_f.pack(fill=tk.BOTH, expand=True)

    step_labels = [
        ("1. Docker", "Start Docker Desktop, then start local services."),
        ("2. Schema", "Apply NebulaGraph schema (create space and tags)."),
        ("3. Data", "Load the graph: synthetic sample or real Wikipedia dump."),
        ("4. Simulation", "Run a simulation step from the graph."),
        ("5. Reasoning", "Run a reasoning query on the graph."),
    ]

    status_var = tk.StringVar(value="Checking...")
    status_lbl = ttk.Label(main_f, textvariable=status_var, wraplength=480)
    status_lbl.pack(anchor=tk.W, pady=(0, 8))

    steps_frame = ttk.Frame(main_f)
    steps_frame.pack(fill=tk.X, pady=4)
    step_text_vars = []
    for i, (title, desc) in enumerate(step_labels):
        var = tk.StringVar(value=f"{title} — {desc}")
        step_text_vars.append(var)
        ttk.Label(steps_frame, textvariable=var, wraplength=480, anchor=tk.W).pack(anchor=tk.W)

    action_btn: tk.Widget = ttk.Button(main_f, text="(none)")
    action_btn.pack(pady=12)

    # Data step: essential buttons only
    data_frame = ttk.Frame(main_f)
    data_btn_sample = ttk.Button(data_frame, text="Run: Generate sample graph")
    data_btn_acquire = ttk.Button(data_frame, text="Run: Acquire dumps")
    data_btn_extract = ttk.Button(data_frame, text="Run: Extraction pipeline")

    # Reasoning: query entry
    query_var = tk.StringVar(value="Wikipedia supports knowledge.")
    query_frame = ttk.Frame(main_f)
    ttk.Label(query_frame, text="Query:").pack(anchor=tk.W)
    query_entry = ttk.Entry(query_frame, textvariable=query_var, width=50)
    query_entry.pack(fill=tk.X, pady=4)
    reason_btn = ttk.Button(query_frame, text="Run reasoning")

    result_text = scrolledtext.ScrolledText(main_f, height=8, width=60, font=("Consolas", 9))
    result_text.pack(fill=tk.BOTH, expand=True, pady=8)

    # Progress bar for operations that may take >5s
    progress_frame = ttk.Frame(main_f)
    progress_label_var = tk.StringVar(value="")
    progress_lbl = ttk.Label(progress_frame, textvariable=progress_label_var)
    progress_bar = ttk.Progressbar(progress_frame, mode="indeterminate", length=320)
    progress_lbl.pack(anchor=tk.W)
    progress_bar.pack(anchor=tk.W, pady=4)

    result_queue: Queue = Queue()

    def show_progress(label: str) -> None:
        progress_label_var.set(label)
        progress_frame.pack(anchor=tk.W, pady=4)
        progress_bar.start(8)

    def hide_progress() -> None:
        progress_bar.stop()
        progress_label_var.set("")
        progress_frame.pack_forget()

    def run_long_task(label: str, task_fn, on_done) -> None:
        """Run task_fn() in a background thread; on_done(ok, msg) runs on main thread when finished."""
        def worker() -> None:
            try:
                ok, msg = task_fn()
                result_queue.put((on_done, ok, msg))
            except Exception as e:
                result_queue.put((on_done, False, str(e)))

        show_progress(label)
        for w in (action_btn, data_btn_sample, data_btn_acquire, data_btn_extract, reason_btn):
            try:
                w.config(state=tk.DISABLED)
            except Exception:
                pass
        threading.Thread(target=worker, daemon=True).start()

    def finish_long_task(on_done, ok: bool, msg: str) -> None:
        hide_progress()
        for w in (action_btn, data_btn_sample, data_btn_acquire, data_btn_extract, reason_btn):
            try:
                w.config(state=tk.NORMAL)
            except Exception:
                pass
        on_done(ok, msg)

    def poll_result_queue() -> None:
        try:
            while True:
                item = result_queue.get_nowait()
                on_done, ok, msg = item
                finish_long_task(on_done, ok, msg)
        except Exception:
            pass
        root.after(200, poll_result_queue)

    root.after(200, poll_result_queue)

    def refresh_state() -> None:
        nonlocal current_step
        docker_ok, _ = check_docker()
        step_done[0] = docker_ok
        schema_ok, _ = check_schema_applied()
        step_done[1] = schema_ok
        data_ok, _ = check_graph_has_data()
        step_done[2] = data_ok
        # Simulation and reasoning we don't auto-detect; they're "done" when user ran them or we could infer
        if not step_done[0]:
            current_step = 0
        elif not step_done[1]:
            current_step = 1
        elif not step_done[2]:
            current_step = 2
        else:
            if current_step < 2:
                current_step = 2
            if current_step == 2:
                current_step = 3  # allow simulation
        update_ui()

    def update_ui() -> None:
        for i, (title, desc) in enumerate(step_labels):
            if step_done[i]:
                step_text_vars[i].set(f"✓ {title} — Done.")
            elif i == current_step or (current_step >= 3 and i in (3, 4)):
                step_text_vars[i].set(f"→ {title} — {desc}")
            else:
                step_text_vars[i].set(f"  {title} — {desc}")

        # Hide all optional panels
        data_frame.pack_forget()
        query_frame.pack_forget()
        action_btn.pack_forget()
        data_btn_sample.pack_forget()
        data_btn_acquire.pack_forget()
        data_btn_extract.pack_forget()
        reason_btn.pack_forget()

        if current_step == 0:
            status_var.set("Start Docker Desktop, then click the button to start local services (NebulaGraph, Redis).")
            action_btn.config(text="Start local services (docker compose up -d)", command=do_docker)
            action_btn.pack(pady=12)
        elif current_step == 1:
            status_var.set("Apply the graph schema to the running NebulaGraph instance.")
            action_btn.config(text="Apply schema (live)", command=do_schema)
            action_btn.pack(pady=12)
        elif current_step == 2:
            status_var.set("Load data into the graph. Choose sample or real corpus.")
            data_frame.pack(anchor=tk.W, pady=8)
            data_btn_sample.pack(pady=4)
            data_btn_acquire.pack(pady=4)
            data_btn_extract.pack(pady=4)
        elif current_step >= 3:
            status_var.set("Graph is ready. Run simulation and/or reasoning.")
            action_btn.config(text="Run simulation (live)", command=do_simulation)
            action_btn.pack(pady=12)
            query_frame.pack(anchor=tk.W, pady=8)
            reason_btn.pack(pady=4)

    def do_docker() -> None:
        compose = ROOT / "docker" / "docker-compose.yml"
        if not compose.exists():
            result_text.delete("1.0", tk.END)
            result_text.insert(tk.END, f"Not found: {compose}\n")
            return

        def task() -> tuple[bool, str]:
            code, out, err = _run(
                ["docker", "compose", "-f", str(compose), "up", "-d"],
                timeout=60,
            )
            msg = out + ("\n" + err if err else "")
            return (code == 0, msg or f"Exit code {code}")

        def on_done(ok: bool, msg: str) -> None:
            result_text.delete("1.0", tk.END)
            result_text.insert(tk.END, msg + "\n")
            if ok:
                result_text.insert(tk.END, "Docker services started. Refreshing...\n")
                step_done[0] = True
                refresh_state()
            else:
                result_text.insert(tk.END, "Failed. Ensure Docker Desktop is running.\n")

        result_text.delete("1.0", tk.END)
        result_text.insert(tk.END, "Starting local services…\n")
        run_long_task("Starting Docker services (docker compose up -d)…", task, on_done)

    def do_schema() -> None:
        def on_done(ok: bool, msg: str) -> None:
            result_text.delete("1.0", tk.END)
            result_text.insert(tk.END, msg + "\n")
            if ok:
                result_text.insert(tk.END, "Schema applied. Next: load data.\n")
                step_done[1] = True
                refresh_state()

        result_text.delete("1.0", tk.END)
        result_text.insert(tk.END, "Applying schema…\n")
        run_long_task("Applying schema (live)…", run_apply_schema, on_done)

    def do_sample() -> None:
        def on_done(ok: bool, msg: str) -> None:
            result_text.delete("1.0", tk.END)
            result_text.insert(tk.END, msg + "\n")
            if ok:
                result_text.insert(tk.END, "Sample loaded. Simulation and reasoning unlocked.\n")
                step_done[2] = True
                refresh_state()

        result_text.delete("1.0", tk.END)
        result_text.insert(tk.END, "Generating sample graph…\n")
        run_long_task("Generating sample graph…", run_generate_sample, on_done)

    def do_acquire() -> None:
        def on_done(ok: bool, msg: str) -> None:
            result_text.delete("1.0", tk.END)
            result_text.insert(tk.END, msg + "\n")
            if not ok:
                result_text.insert(tk.END, "Acquire failed. Check network or try sample instead.\n")
            else:
                result_text.insert(tk.END, "Dumps acquired. Click 'Run: Extraction pipeline' to load into graph.\n")

        result_text.delete("1.0", tk.END)
        result_text.insert(tk.END, "Acquiring dumps…\n")
        run_long_task("Acquiring Wikipedia dumps…", run_acquire_dumps, on_done)

    def do_extract() -> None:
        inp = ROOT / "data" / "raw" / "wikipedia" / "abstracts.txt"
        if not inp.exists():
            result_text.delete("1.0", tk.END)
            result_text.insert(tk.END, f"Missing {inp}. Run 'Acquire dumps' first.\n")
            return

        def on_done(ok: bool, msg: str) -> None:
            result_text.delete("1.0", tk.END)
            result_text.insert(tk.END, msg + "\n")
            if ok:
                result_text.insert(tk.END, "Pipeline done. Simulation and reasoning unlocked.\n")
                step_done[2] = True
                refresh_state()

        result_text.delete("1.0", tk.END)
        result_text.insert(tk.END, "Running extraction pipeline…\n")
        run_long_task("Running extraction pipeline (live)…", run_extraction_pipeline, on_done)

    def do_simulation() -> None:
        def on_done(ok: bool, msg: str) -> None:
            result_text.delete("1.0", tk.END)
            result_text.insert(tk.END, msg + "\n")

        result_text.delete("1.0", tk.END)
        result_text.insert(tk.END, "Running simulation…\n")
        run_long_task("Running simulation (live)…", run_simulation, on_done)

    def do_reasoning() -> None:
        q = query_var.get()
        if not q.strip():
            result_text.delete("1.0", tk.END)
            result_text.insert(tk.END, "Enter a query.\n")
            return

        def on_done(ok: bool, msg: str) -> None:
            result_text.delete("1.0", tk.END)
            result_text.insert(tk.END, msg + "\n")

        result_text.delete("1.0", tk.END)
        result_text.insert(tk.END, "Running reasoning…\n")
        run_long_task("Running reasoning (live)…", lambda: run_reasoning(q), on_done)

    data_btn_sample.config(command=do_sample)
    data_btn_acquire.config(command=do_acquire)
    data_btn_extract.config(command=do_extract)
    reason_btn.config(command=do_reasoning)

    # Debug section (always)
    sep = ttk.Separator(main_f, orient=tk.HORIZONTAL)
    sep.pack(fill=tk.X, pady=8)
    ttk.Label(main_f, text="Debug (copy-paste for support):").pack(anchor=tk.W)
    debug_btn = ttk.Button(main_f, text="Generate debug report")
    debug_btn.pack(side=tk.LEFT, padx=(0, 8))
    copy_btn = ttk.Button(main_f, text="Copy report to clipboard")

    def on_debug() -> None:
        result_text.delete("1.0", tk.END)
        result_text.insert(tk.END, get_debug_report())

    def on_copy() -> None:
        content = result_text.get("1.0", tk.END)
        root.clipboard_clear()
        root.clipboard_append(content)
        messagebox.showinfo("Debug", "Report copied to clipboard.")

    debug_btn.config(command=on_debug)
    copy_btn.config(command=on_copy)
    copy_btn.pack(side=tk.LEFT)

    root.after(300, refresh_state)
    root.mainloop()


if __name__ == "__main__":
    main()
