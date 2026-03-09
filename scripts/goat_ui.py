"""
GOAT Engine UI – Install wizard (step-by-step setup) and full dashboard with all actions.
Features real-time streaming output and progress bars for every operation.
Run:  python scripts/goat_ui.py   (from repo root)
"""
from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

# Debug tracker: thread-safe log of UI actions and task outcomes (for pop-out and copy)
_debug_tracker_lines: list[str] = []
_debug_tracker_lock = threading.Lock()
_MAX_TRACKER_LINES = 2000


def debug_tracker_log(message: str, level: str = "INFO") -> None:
    """Append a timestamped line to the debug tracker. Safe to call from any thread."""
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S.%f")[:-3]
    with _debug_tracker_lock:
        _debug_tracker_lines.append(f"[{ts}] [{level}] {message}")
        if len(_debug_tracker_lines) > _MAX_TRACKER_LINES:
            _debug_tracker_lines[:] = _debug_tracker_lines[-_MAX_TRACKER_LINES:]


def get_debug_tracker_text() -> str:
    """Return full tracker log as a single string."""
    with _debug_tracker_lock:
        return "\n".join(_debug_tracker_lines) if _debug_tracker_lines else "(Debug tracker is empty.)"

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

ENV = os.environ.copy()
ENV["PYTHONPATH"] = str(ROOT)
ENV["PYTHONIOENCODING"] = "utf-8"


def _run(cmd: list[str], cwd: Path | None = None, timeout: int = 120) -> tuple[int, str, str]:
    """Run command and return (returncode, stdout, stderr)."""
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


def _run_streaming(
    cmd: list[str],
    line_queue: queue.Queue,
    cwd: Path | None = None,
    timeout: int = 600,
) -> tuple[int, str, str]:
    """Run command; push each line of stdout/stderr to line_queue as (line, 'out'|'err'). Returns (code, full_stdout, full_stderr)."""
    out_lines: list[str] = []
    err_lines: list[str] = []
    proc = None
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=cwd or ROOT,
            env=ENV,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        def read_stream(stream, stream_name: str, into: list[str]) -> None:
            for line in iter(stream.readline, ""):
                into.append(line)
                try:
                    line_queue.put((line.rstrip(), stream_name))
                except Exception:
                    pass

        t_out = threading.Thread(target=read_stream, args=(proc.stdout, "out", out_lines), daemon=True)
        t_err = threading.Thread(target=read_stream, args=(proc.stderr, "err", err_lines), daemon=True)
        t_out.start()
        t_err.start()
        proc.wait(timeout=timeout)
        t_out.join(timeout=2)
        t_err.join(timeout=2)
        return proc.returncode or 0, "".join(out_lines), "".join(err_lines)
    except subprocess.TimeoutExpired:
        if proc:
            try:
                proc.kill()
            except Exception:
                pass
        try:
            line_queue.put(("(Process timed out.)", "err"))
        except Exception:
            pass
        return -1, "".join(out_lines), "".join(err_lines) + "\nTimeout"
    except Exception as e:
        try:
            line_queue.put((str(e), "err"))
        except Exception:
            pass
        return -1, "", str(e)


def check_docker() -> tuple[bool, str]:
    code, out, err = _run(["docker", "info"], timeout=10)
    return (code == 0, "Docker is running." if code == 0 else (err or out or "Docker not found or not running."))


def check_schema_applied() -> tuple[bool, str]:
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


def get_graph_explainable_summary(live: bool, concept_limit: int = 400, wave_limit: int = 80) -> str:
    """Fetch concepts and waves from the graph and return a short summary of what the system can explain."""
    try:
        from src.graph.client import NebulaGraphClient
        client = NebulaGraphClient(ROOT / "configs" / "graph.yaml", dry_run_override=not live if live else None)
        try:
            nodes = client.list_nodes(limit=concept_limit)
            waves = client.list_waves(limit=wave_limit)
        finally:
            client.close()
    except Exception as e:
        return f"Could not load summary: {str(e)[:200]}"
    if not nodes and not waves:
        return "Graph is empty. Load data (sample or Wikipedia extraction) to see what the system can explain."
    lines = ["The system can explain queries using the following knowledge mapped from the graph:\n"]
    if nodes:
        labels = [n.label.strip() for n in nodes if n and (n.label or "").strip()]
        unique = list(dict.fromkeys(labels))[:80]
        sample = ", ".join(unique[:25])
        if len(unique) > 25:
            sample += f", ... (+{len(unique) - 25} more)"
        lines.append(f"Concepts ({len(labels)} total): {sample}")
    if waves:
        wave_labels = [w.label.strip()[:70] for w in waves if w and (w.label or "").strip()]
        lines.append(f"\nCognitive contexts / waves ({len(waves)}):")
        for wl in wave_labels[:10]:
            lines.append(f"  • {wl}")
        if len(wave_labels) > 10:
            lines.append(f"  ... and {len(wave_labels) - 10} more")
    lines.append("\nUse Reasoning (above) to ask questions; the system will use these concepts and relations.")
    return "\n".join(lines)


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
    root.title("GOAT Engine — Thinking System")
    root.minsize(720, 620)
    root.geometry("820x680")
    root.configure(bg="#1a1b26")

    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except Exception:
        pass
    style.configure("TFrame", background="#1a1b26")
    style.configure("TLabel", background="#1a1b26", foreground="#c0caf5", padding=(4, 4))
    style.configure("TButton", padding=(10, 6))
    style.configure("Accent.TButton", background="#7aa2f7", foreground="#1a1b26", padding=(14, 8))
    style.map("Accent.TButton", background=[("active", "#89b4fa"), ("pressed", "#6b8cd4")])
    style.configure("Dim.TLabel", background="#1a1b26", foreground="#565f89", padding=(4, 0))
    style.configure("TLabelframe", background="#1a1b26")
    style.configure("TLabelframe.Label", background="#1a1b26", foreground="#c0caf5")
    style.configure("TNotebook", background="#1a1b26")
    style.configure("TNotebook.Tab", background="#24283b", foreground="#c0caf5", padding=(12, 6))

    # Shared output and progress
    line_queue: queue.Queue = queue.Queue()
    progress_label_var = tk.StringVar(value="")
    running = threading.Event()

    main_f = ttk.Frame(root, padding=16)
    main_f.pack(fill=tk.BOTH, expand=True)

    # Header and content slot (wizard/dashboard) - packed first so they sit above output
    header_f = ttk.Frame(main_f)
    header_f.pack(fill=tk.X)
    ttk.Label(header_f, text="GOAT Engine — Thinking System", font=("Segoe UI", 14, "bold")).pack(side=tk.LEFT)
    ttk.Separator(main_f, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=(4, 8))
    wizard_container = ttk.Frame(main_f)
    dashboard_container = ttk.Frame(main_f)
    wizard_container.pack(fill=tk.BOTH, expand=True)

    # Output area (below content)
    ttk.Label(main_f, text="Output", style="TLabel").pack(anchor=tk.W, pady=(8, 2))
    result_text = scrolledtext.ScrolledText(
        main_f,
        height=12,
        width=88,
        font=("Consolas", 9),
        bg="#16161e",
        fg="#a9b1d6",
        insertbackground="#a9b1d6",
        relief=tk.FLAT,
        padx=10,
        pady=8,
    )
    result_text.pack(fill=tk.BOTH, expand=True, pady=(0, 8))

    # Progress bar (real-time)
    progress_frame = ttk.Frame(main_f)
    progress_lbl = ttk.Label(progress_frame, textvariable=progress_label_var)
    progress_bar = ttk.Progressbar(progress_frame, mode="indeterminate", length=400)

    def show_progress(label: str) -> None:
        progress_label_var.set(label)
        progress_frame.pack(anchor=tk.W, pady=4)
        progress_bar.start(8)
        running.set()

    def hide_progress() -> None:
        progress_bar.stop()
        progress_label_var.set("")
        progress_frame.pack_forget()
        running.clear()

    def append_output(line: str, is_err: bool = False) -> None:
        start = result_text.index(tk.END)
        result_text.insert(tk.END, line + "\n")
        if is_err:
            result_text.tag_add("stderr", start, tk.END)
        result_text.see(tk.END)
        result_text.update_idletasks()

    result_text.tag_configure("stderr", foreground="#f7768e")

    def open_debug_tracker_popout() -> None:
        """Open a pop-out window with the debug tracker log and Copy to clipboard."""
        debug_tracker_log("DEBUG_TRACKER: pop-out opened")
        top = tk.Toplevel(root)
        top.title("GOAT — Debug tracker")
        top.minsize(500, 300)
        top.geometry("720x420")
        top.configure(bg="#1a1b26")
        f = ttk.Frame(top, padding=10)
        f.pack(fill=tk.BOTH, expand=True)
        ttk.Label(f, text="Debug tracker — actions, tasks, and navigation log", style="TLabel").pack(anchor=tk.W)
        log_text = scrolledtext.ScrolledText(
            f,
            height=20,
            width=88,
            font=("Consolas", 9),
            bg="#16161e",
            fg="#a9b1d6",
            relief=tk.FLAT,
            padx=8,
            pady=6,
        )
        log_text.pack(fill=tk.BOTH, expand=True, pady=(4, 8))
        def refresh_popout() -> None:
            log_text.delete("1.0", tk.END)
            log_text.insert(tk.END, get_debug_tracker_text())
        refresh_popout()
        btn_f = ttk.Frame(f)
        btn_f.pack(anchor=tk.W)
        ttk.Button(btn_f, text="Refresh", command=refresh_popout).pack(side=tk.LEFT, padx=(0, 8))
        def copy_tracker() -> None:
            root.clipboard_clear()
            root.clipboard_append(get_debug_tracker_text())
            messagebox.showinfo("Debug tracker", "Debug tracker log copied to clipboard.")
        ttk.Button(btn_f, text="Copy to clipboard", command=copy_tracker).pack(side=tk.LEFT, padx=(0, 8))

    def run_task(
        label: str,
        cmd: list[str],
        on_done: Callable[[bool, str], None],
        timeout: int = 600,
        clear_before: bool = True,
    ) -> None:
        """Run cmd with streaming output; on_done(success, full_output) on main thread."""

        cmd_str = " ".join(cmd)
        debug_tracker_log(f"TASK_START: {label} | {cmd_str[:200]}{'...' if len(cmd_str) > 200 else ''}")

        def worker() -> None:
            if clear_before:
                root.after(0, lambda: (result_text.delete("1.0", tk.END), result_text.insert(tk.END, f">>> {' '.join(cmd)}\n\n")))
            root.after(0, lambda: show_progress(label))
            code, out, err = _run_streaming(cmd, line_queue, cwd=ROOT, timeout=timeout)
            full = (out + "\n" + err).strip() if err else out
            success = code == 0
            level = "ERROR" if not success else "INFO"
            root.after(0, lambda: debug_tracker_log(f"TASK_END: {label} | success={success} exitcode={code}", level=level))
            root.after(0, lambda: (hide_progress(), on_done(success, full)))

        threading.Thread(target=worker, daemon=True).start()

    def pump_queue() -> None:
        try:
            while True:
                line, kind = line_queue.get_nowait()
                append_output(line, is_err=(kind == "err"))
        except queue.Empty:
            pass
        root.after(100, pump_queue)

    root.after(100, pump_queue)

    # ---------- Install wizard ----------
    wizard_step = tk.IntVar(value=0)
    wizard_done = [False, False, False, False, False]  # Docker, Schema, Data, Verify, Done

    def refresh_wizard_checks() -> None:
        d_ok, _ = check_docker()
        wizard_done[0] = d_ok
        s_ok, _ = check_schema_applied()
        wizard_done[1] = s_ok
        g_ok, _ = check_graph_has_data()
        wizard_done[2] = g_ok
        wizard_done[3] = True  # Verify is optional

    def show_wizard() -> None:
        if running.is_set():
            return
        debug_tracker_log("NAV: Open wizard")
        dashboard_container.pack_forget()
        wizard_container.pack(fill=tk.BOTH, expand=True)
        show_wizard_step(wizard_step.get())

    def show_dashboard() -> None:
        if running.is_set():
            return
        debug_tracker_log("NAV: Open dashboard")
        wizard_container.pack_forget()
        dashboard_container.pack(fill=tk.BOTH, expand=True)
        refresh_wizard_checks()
        build_dashboard()

    def show_wizard_step(step: int) -> None:
        # Don't change step while a long task is running (e.g. Acquire dumps)
        if running.is_set():
            return
        debug_tracker_log(f"WIZARD_STEP: {step}")
        for w in wizard_container.winfo_children():
            w.destroy()
        wizard_step.set(step)

        # Step content
        inner = ttk.Frame(wizard_container)
        inner.pack(fill=tk.BOTH, expand=True, pady=8)

        if step == 0:
            ttk.Label(inner, text="Welcome to GOAT Engine", font=("Segoe UI", 14, "bold")).pack(anchor=tk.W)
            ttk.Label(inner, text="This wizard will guide you through:\n  1. Starting Docker and local services\n  2. Applying the graph schema\n  3. Loading data (sample or real)\n  4. Verifying the setup", style="Dim.TLabel", justify=tk.LEFT).pack(anchor=tk.W, pady=8)
            ttk.Button(inner, text="Start wizard", style="Accent.TButton", command=lambda: show_wizard_step(1)).pack(pady=12)
            def skip():
                show_dashboard()
                result_text.delete("1.0", tk.END)
                result_text.insert(tk.END, "Skipped wizard. Use the dashboard to run any step.\n")
            ttk.Button(inner, text="Skip to dashboard", command=skip).pack(pady=4)
            return

        if step == 1:
            ttk.Label(inner, text="Step 1: Docker", font=("Segoe UI", 12, "bold")).pack(anchor=tk.W)
            ttk.Label(inner, text="Ensure Docker Desktop is running. Then start local services (NebulaGraph, Redis).", style="Dim.TLabel", wraplength=520).pack(anchor=tk.W, pady=4)
            ttk.Button(inner, text="Start local services (docker compose up -d)", style="Accent.TButton", command=do_wizard_docker).pack(pady=6)
            ttk.Button(inner, text="Check Docker", command=do_check_docker).pack(pady=4)
        elif step == 2:
            ttk.Label(inner, text="Step 2: Schema", font=("Segoe UI", 12, "bold")).pack(anchor=tk.W)
            ttk.Label(inner, text="Apply the graph schema to NebulaGraph (creates space and tags).", style="Dim.TLabel", wraplength=520).pack(anchor=tk.W, pady=4)
            ttk.Button(inner, text="Apply schema (dry-run)", command=lambda: do_apply_schema(True)).pack(pady=4)
            ttk.Button(inner, text="Apply schema (live)", style="Accent.TButton", command=lambda: do_apply_schema(False)).pack(pady=6)
        elif step == 3:
            ttk.Label(inner, text="Step 3: Data", font=("Segoe UI", 12, "bold")).pack(anchor=tk.W)
            ttk.Label(inner, text="Load the graph: generate a sample or acquire real dumps and run extraction.", style="Dim.TLabel", wraplength=520).pack(anchor=tk.W, pady=4)
            ttk.Button(inner, text="Generate sample graph (3000 nodes)", style="Accent.TButton", command=do_wizard_sample).pack(pady=4)
            ttk.Button(inner, text="Acquire dumps (Wikipedia API)", command=do_wizard_acquire).pack(pady=4)
            ttk.Button(inner, text="Run extraction pipeline", command=do_wizard_extract).pack(pady=4)
        elif step == 4:
            ttk.Label(inner, text="Step 4: Verify (optional)", font=("Segoe UI", 12, "bold")).pack(anchor=tk.W)
            ttk.Label(inner, text="Inspect the graph to confirm data and see what the system can explain.", style="Dim.TLabel", wraplength=520).pack(anchor=tk.W, pady=4)
            ttk.Button(inner, text="Dump graph stats", command=do_dump_stats).pack(pady=2)
            ttk.Button(inner, text="Show what the system can explain", command=do_show_explainable).pack(pady=2)
        elif step == 5:
            ttk.Label(inner, text="Setup complete", font=("Segoe UI", 12, "bold")).pack(anchor=tk.W)
            ttk.Label(inner, text="You can now run simulation, reasoning, and all other actions from the dashboard.", style="Dim.TLabel", wraplength=520).pack(anchor=tk.W, pady=8)
            ttk.Button(inner, text="Open dashboard", style="Accent.TButton", command=show_dashboard).pack(pady=12)

        # Back / Next
        nav = ttk.Frame(inner)
        nav.pack(fill=tk.X, pady=(16, 0))
        if step > 1:
            ttk.Button(nav, text="Back", command=lambda: show_wizard_step(step - 1)).pack(side=tk.LEFT, padx=(0, 8))
        if step < 5 and step > 0:
            next_enabled = (step == 1 and wizard_done[0]) or (step == 2 and wizard_done[1]) or (step == 3 and wizard_done[2]) or step == 4
            btn = ttk.Button(nav, text="Next", style="Accent.TButton" if next_enabled else "TButton", command=lambda: show_wizard_step(step + 1))
            btn.pack(side=tk.LEFT)
            if not next_enabled and step in (1, 2, 3):
                btn.config(state=tk.DISABLED)

    def do_check_docker() -> None:
        debug_tracker_log("ACTION: Check Docker")
        result_text.delete("1.0", tk.END)
        ok, msg = check_docker()
        result_text.insert(tk.END, msg + "\n")
        if ok:
            wizard_done[0] = True
            show_wizard_step(1)

    def do_wizard_docker() -> None:
        compose = ROOT / "docker" / "docker-compose.yml"
        if not compose.exists():
            result_text.delete("1.0", tk.END)
            result_text.insert(tk.END, f"Not found: {compose}\n")
            return

        def on_done(success: bool, _: str) -> None:
            if success:
                wizard_done[0] = True
                refresh_wizard_checks()
                show_wizard_step(1)

        run_task(
            "Starting Docker services…",
            ["docker", "compose", "-f", compose.as_posix(), "up", "-d"],
            on_done,
            timeout=90,
        )

    def do_apply_schema(dry: bool) -> None:
        cmd = [sys.executable, str(ROOT / "scripts" / "apply_schema.py")]
        if dry:
            cmd.append("--dry-run")
        else:
            cmd.append("--live")

        def on_done(success: bool, _: str) -> None:
            if success and not dry:
                wizard_done[1] = True
                refresh_wizard_checks()
                show_wizard_step(2)

        run_task("Applying schema…", cmd, on_done, timeout=45)

    def do_wizard_sample() -> None:
        cmd = [
            sys.executable, str(ROOT / "scripts" / "generate_sample_100k.py"),
            "--node-count", "3000", "--edge-count", "8000", "--live",
        ]

        def on_done(success: bool, _: str) -> None:
            if success:
                wizard_done[2] = True
                refresh_wizard_checks()
                show_wizard_step(3)

        run_task("Generating sample graph…", cmd, on_done, timeout=120)

    def do_wizard_acquire() -> None:
        (ROOT / "data" / "raw").mkdir(parents=True, exist_ok=True)
        cmd = [
            sys.executable, str(ROOT / "scripts" / "acquire_dumps.py"),
            "--output-dir", str(ROOT / "data" / "raw"), "--max-docs", "150",
        ]

        def on_done(success: bool, _: str) -> None:
            if success:
                append_output("Acquire done. Run 'Run extraction pipeline' to load into graph.", is_err=False)

        run_task("Acquiring dumps…", cmd, on_done, timeout=300)

    def do_wizard_extract() -> None:
        inp = ROOT / "data" / "raw" / "wikipedia" / "abstracts.txt"
        if not inp.exists():
            result_text.delete("1.0", tk.END)
            result_text.insert(tk.END, f"Missing {inp}. Run 'Acquire dumps' first.\n")
            return

        def on_done(success: bool, _: str) -> None:
            if success:
                wizard_done[2] = True
                refresh_wizard_checks()
                show_wizard_step(3)

        run_task("Running extraction pipeline…", [sys.executable, "-m", "src.ingestion.extraction_pipeline", "--input-path", str(inp), "--live"], on_done, timeout=600)

    def do_dump_stats() -> None:
        run_task("Dump graph stats…", [sys.executable, str(ROOT / "scripts" / "dump_graph_stats.py"), "--live"], lambda ok, msg: None, timeout=30)

    def do_show_explainable() -> None:
        """Show what the system can explain (concepts/waves from graph) in the output area."""
        debug_tracker_log("ACTION: Show what the system can explain (wizard)")
        result_text.delete("1.0", tk.END)
        result_text.insert(tk.END, "Loading what the system can explain from graph…\n")
        def worker() -> None:
            summary = get_graph_explainable_summary(live=True)
            root.after(0, lambda: (result_text.delete("1.0", tk.END), result_text.insert(tk.END, summary)))
        threading.Thread(target=worker, daemon=True).start()

    # ---------- Dashboard (all actions) ----------
    def build_dashboard() -> None:
        for w in dashboard_container.winfo_children():
            w.destroy()
        canvas = tk.Canvas(dashboard_container, bg="#1a1b26", highlightthickness=0)
        scroll_f = ttk.Frame(canvas)
        scroll_f.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scroll_f, anchor=tk.NW)

        def add_section(title: str) -> ttk.Frame:
            lab = ttk.LabelFrame(scroll_f, text=title)
            lab.pack(fill=tk.X, pady=(0, 10))
            return lab

        # Infrastructure
        inf = add_section("Infrastructure")
        ttk.Button(inf, text="Start Docker services", command=lambda: run_task("Starting Docker…", ["docker", "compose", "-f", (ROOT / "docker" / "docker-compose.yml").as_posix(), "up", "-d"], lambda ok, m: None, 90)).pack(side=tk.LEFT, padx=(0, 8), pady=4)
        ttk.Button(inf, text="Check Docker", command=lambda: (result_text.delete("1.0", tk.END), result_text.insert(tk.END, check_docker()[1] + "\n"))).pack(side=tk.LEFT, padx=(0, 8), pady=4)

        # Schema
        sch = add_section("Schema")
        ttk.Button(sch, text="Apply schema (dry-run)", command=lambda: run_task("Schema dry-run…", [sys.executable, str(ROOT / "scripts" / "apply_schema.py"), "--dry-run"], lambda ok, m: None, 30)).pack(side=tk.LEFT, padx=(0, 8), pady=4)
        ttk.Button(sch, text="Apply schema (live)", command=lambda: run_task("Applying schema (live)…", [sys.executable, str(ROOT / "scripts" / "apply_schema.py"), "--live"], lambda ok, m: None, 45)).pack(side=tk.LEFT, padx=(0, 8), pady=4)

        # Data
        dat = add_section("Data")
        ttk.Button(dat, text="Generate sample (3k nodes)", command=lambda: run_task("Generating sample…", [sys.executable, str(ROOT / "scripts" / "generate_sample_100k.py"), "--node-count", "3000", "--edge-count", "8000", "--live"], lambda ok, m: None, 120)).pack(side=tk.LEFT, padx=(0, 8), pady=4)
        ttk.Button(dat, text="Acquire dumps (150 docs)", command=lambda: run_task("Acquiring dumps…", [sys.executable, str(ROOT / "scripts" / "acquire_dumps.py"), "--output-dir", str(ROOT / "data" / "raw"), "--max-docs", "150"], lambda ok, m: None, 300)).pack(side=tk.LEFT, padx=(0, 8), pady=4)
        ttk.Button(dat, text="Run extraction pipeline", command=lambda: run_task("Extraction…", [sys.executable, "-m", "src.ingestion.extraction_pipeline", "--input-path", str(ROOT / "data" / "raw" / "wikipedia" / "abstracts.txt"), "--live"], lambda ok, m: None, 600)).pack(side=tk.LEFT, padx=(0, 8), pady=4)

        # Verification
        ver = add_section("Verification")
        ttk.Button(ver, text="Query wave (list)", command=lambda: run_task("List waves…", [sys.executable, str(ROOT / "scripts" / "query_wave.py"), "--list", "--live"], lambda ok, m: None, 30)).pack(side=tk.LEFT, padx=(0, 8), pady=4)
        ttk.Button(ver, text="Dump graph stats", command=lambda: run_task("Graph stats…", [sys.executable, str(ROOT / "scripts" / "dump_graph_stats.py"), "--live"], lambda ok, m: None, 30)).pack(side=tk.LEFT, padx=(0, 8), pady=4)
        exp_f = ttk.Frame(ver)
        exp_f.pack(fill=tk.X, pady=4)
        ttk.Label(exp_f, text="Export subgraph — concept:").pack(side=tk.LEFT, padx=(0, 4))
        export_concept_var = tk.StringVar(value="Python")
        ttk.Entry(exp_f, textvariable=export_concept_var, width=16).pack(side=tk.LEFT, padx=(0, 8))
        def do_export() -> None:
            c = export_concept_var.get().strip() or "Concept"
            out_j = str(ROOT / "examples" / "export_out.json")
            out_p = str(ROOT / "examples" / "export_out.png")
            run_task("Export subgraph…", [sys.executable, str(ROOT / "scripts" / "export_subgraph.py"), "--concept", c, "--live", "--output", out_j, "--plot", out_p], lambda ok, m: None, 60)
        ttk.Button(exp_f, text="Export JSON + PNG", command=do_export).pack(side=tk.LEFT, padx=(0, 8))

        # What the system can explain (context from wiki dump mapped to graph)
        explain_section = add_section("What the system can explain")
        ttk.Label(explain_section, text="Concepts and cognitive contexts currently in the graph (from Wikipedia dump / sample):", style="Dim.TLabel", wraplength=520).pack(anchor=tk.W)
        explain_text = scrolledtext.ScrolledText(
            explain_section,
            height=10,
            width=72,
            font=("Consolas", 9),
            bg="#16161e",
            fg="#a9b1d6",
            relief=tk.FLAT,
            padx=8,
            pady=6,
            state=tk.DISABLED,
        )
        explain_text.pack(fill=tk.X, pady=4)
        explain_btn_frame = ttk.Frame(explain_section)
        explain_btn_frame.pack(anchor=tk.W)
        def set_explain_content(text: str) -> None:
            explain_text.config(state=tk.NORMAL)
            explain_text.delete("1.0", tk.END)
            explain_text.insert(tk.END, text)
            explain_text.config(state=tk.DISABLED)
        def refresh_explain() -> None:
            debug_tracker_log("ACTION: Refresh 'What the system can explain' (dashboard)")
            set_explain_content("Loading from graph…")
            def worker() -> None:
                summary = get_graph_explainable_summary(live=True)
                root.after(0, lambda: set_explain_content(summary))
            threading.Thread(target=worker, daemon=True).start()
        ttk.Button(explain_btn_frame, text="Refresh (live graph)", command=refresh_explain).pack(side=tk.LEFT, padx=(0, 8), pady=2)
        set_explain_content("Click 'Refresh (live graph)' to load what the system can explain from the current graph.")

        # Gravity demo
        grav = add_section("Gravity / simulation demo")
        ttk.Button(grav, text="Gravity demo (100 iters, JSON+PNG)", command=lambda: run_task("Gravity demo…", [sys.executable, str(ROOT / "scripts" / "run_gravity_demo.py"), "--iterations", "100", "--output", str(ROOT / "examples" / "gravity_out.json"), "--plot", str(ROOT / "examples" / "gravity_out.png")], lambda ok, m: None, 120)).pack(side=tk.LEFT, padx=(0, 8), pady=4)
        ttk.Button(grav, text="Gravity demo (live graph)", command=lambda: run_task("Gravity demo (live)…", [sys.executable, str(ROOT / "scripts" / "run_gravity_demo.py"), "--live", "--iterations", "50", "--output", str(ROOT / "examples" / "gravity_live.json"), "--plot", str(ROOT / "examples" / "gravity_live.png")], lambda ok, m: None, 120)).pack(side=tk.LEFT, padx=(0, 8), pady=4)
        ttk.Button(grav, text="Run simulation (live)", command=lambda: run_task("Simulation…", [sys.executable, str(ROOT / "scripts" / "run_simulation.py"), "--live", "--edge-limit", "500"], lambda ok, m: None, 90)).pack(side=tk.LEFT, padx=(0, 8), pady=4)

        # Reasoning
        rea = add_section("Reasoning")
        rea_f = ttk.Frame(rea)
        rea_f.pack(fill=tk.X, pady=4)
        ttk.Label(rea_f, text="Query:").pack(side=tk.LEFT, padx=(0, 4))
        reasoning_query_var = tk.StringVar(value="Wikipedia supports free knowledge.")
        ttk.Entry(rea_f, textvariable=reasoning_query_var, width=48).pack(side=tk.LEFT, padx=(0, 8), fill=tk.X, expand=True)
        def do_reasoning() -> None:
            q = reasoning_query_var.get().strip()
            if not q:
                result_text.delete("1.0", tk.END)
                result_text.insert(tk.END, "Enter a query.\n")
                return
            run_task("Reasoning…", [sys.executable, str(ROOT / "scripts" / "run_reasoning_demo.py"), "--live", "--query", q], lambda ok, m: None, 60)
        ttk.Button(rea_f, text="Run reasoning", style="Accent.TButton", command=do_reasoning).pack(side=tk.LEFT, padx=(0, 8))

        # Debug
        dbg = add_section("Debug")
        ttk.Button(dbg, text="Debug tracker (pop-out)", command=open_debug_tracker_popout).pack(side=tk.LEFT, padx=(0, 8), pady=4)
        ttk.Button(dbg, text="Generate debug report", command=lambda: (debug_tracker_log("ACTION: Generate debug report"), result_text.delete("1.0", tk.END), result_text.insert(tk.END, get_debug_report()))).pack(side=tk.LEFT, padx=(0, 8), pady=4)
        def copy_report() -> None:
            root.clipboard_clear()
            root.clipboard_append(result_text.get("1.0", tk.END))
            debug_tracker_log("ACTION: Copy output to clipboard")
            messagebox.showinfo("Debug", "Report copied to clipboard.")
        ttk.Button(dbg, text="Copy output to clipboard", command=copy_report).pack(side=tk.LEFT, padx=(0, 8), pady=4)

        def on_scroll(event) -> None:
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        canvas.bind_all("<MouseWheel>", on_scroll)
        sb = ttk.Scrollbar(dashboard_container, orient=tk.VERTICAL, command=canvas.yview)
        canvas.configure(yscrollcommand=sb.set)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        ttk.Button(dashboard_container, text="Back to wizard", command=show_wizard).pack(anchor=tk.W, pady=4)

    ttk.Button(header_f, text="Debug tracker", command=open_debug_tracker_popout).pack(side=tk.RIGHT, padx=4)
    ttk.Button(header_f, text="Open wizard", command=show_wizard).pack(side=tk.RIGHT, padx=4)
    ttk.Button(header_f, text="Dashboard", command=show_dashboard).pack(side=tk.RIGHT)

    refresh_wizard_checks()
    debug_tracker_log("APP_START: GOAT UI started")
    show_wizard_step(0)
    root.mainloop()


if __name__ == "__main__":
    main()
