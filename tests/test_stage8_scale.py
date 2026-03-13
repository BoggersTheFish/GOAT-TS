"""Stage 8: Optimization and scaling — larger graph, efficiency metrics."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_demo_loop_scale_medium_graph() -> None:
    """Demo loop runs with synthetic graph (medium size) and completes."""
    from src.agi_loop.demo_loop import run_demo
    from src.graph.client import NebulaGraphClient

    client = NebulaGraphClient(config_path=str(ROOT / "configs" / "graph.yaml"), dry_run_override=True)
    try:
        nodes, edges, summary = run_demo(
            client,
            seed_ids=[],
            seed_labels=["concept"],
            ticks=3,
            enable_forces=False,
            config_path=str(ROOT / "configs" / "graph.yaml"),
        )
    finally:
        client.close()
    assert len(nodes) >= 1
    assert summary["ticks"] == 3


def test_gpu_benchmark_script_exits_zero() -> None:
    """run_gpu_benchmark.py runs (CPU fallback ok) and exits 0."""
    import subprocess
    import os
    env = {**os.environ, "PYTHONPATH": str(ROOT), "GOAT_USE_GPU": "0"}
    r = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "run_gpu_benchmark.py")],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=60,
        env=env,
    )
    assert r.returncode == 0


def test_efficiency_metrics_exist() -> None:
    """Efficiency metrics (ticks_per_second, graph_size_nodes) are defined."""
    from src.monitoring import metrics
    assert hasattr(metrics, "ticks_per_second")
    assert hasattr(metrics, "graph_size_nodes")
