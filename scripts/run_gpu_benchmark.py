"""
Stage 8: Quick GPU benchmark — run a short cognition loop with forces and report timing.
Set configs/simulation.yaml use_gpu: true or GOAT_USE_GPU=1 to test CUDA path.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    os.environ.setdefault("GOAT_USE_GPU", "0")
    from src.agi_loop.demo_loop import run_demo
    from src.graph.client import NebulaGraphClient

    config_path = str(ROOT / "configs" / "graph.yaml")
    client = NebulaGraphClient(config_path=config_path, dry_run_override=True)
    ticks = 3
    t0 = time.perf_counter()
    try:
        run_demo(
            client,
            seed_ids=[],
            seed_labels=["concept"],
            ticks=ticks,
            enable_forces=True,
            config_path=config_path,
        )
    finally:
        client.close()
    elapsed = time.perf_counter() - t0
    tps = ticks / elapsed if elapsed > 0 else 0
    print(f"GPU benchmark: ticks={ticks}, elapsed={elapsed:.3f}s, ticks/sec={tps:.4f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
