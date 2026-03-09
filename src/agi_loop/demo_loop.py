"""
Minimal standalone demo: multi-tick TS cognition cycle using spreading activation,
memory decay/state transitions, and optional gravity. Strict error handling — no
silent fallbacks. Run: python -m src.agi_loop.demo_loop --help
"""
from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np

from src.activation import (
    activate_and_propagate,
    get_activated_subgraph,
)
from src.graph.client import NebulaGraphClient
from src.graph.models import Edge, MemoryState, Node
from src.memory_manager import memory_tick
from src.simulation.gravity import (
    build_state,
    compute_forces,
    update_positions,
)

logger = logging.getLogger(__name__)

# Defaults
DEFAULT_TICKS = 20
DEFAULT_DECAY_RATE = 0.95
ACTIVE_THRESHOLD = 0.5
DORMANT_THRESHOLD = 0.1
TICKS_TO_DEEP = 3
SPREAD_DECAY = 0.1
SPREAD_THRESHOLD = 0.1
SPREAD_MAX_HOPS = 5
NODE_LIMIT = 2000
EDGE_LIMIT = 5000


def _ensure_agi_loop_deps() -> None:
    """Verify required modules and raise with clear context if missing."""
    try:
        from src.activation import propagate_spreading_activation  # noqa: F401
    except ImportError as e:
        raise ImportError(
            "src.activation is required for demo_loop (propagate_spreading_activation). "
            f"Import failed: {e}"
        ) from e
    try:
        from src.memory_manager import apply_decay_and_transitions  # noqa: F401
    except ImportError as e:
        raise ImportError(
            "src.memory_manager is required for demo_loop. "
            f"Import failed: {e}"
        ) from e


def _generate_synthetic_graph(num_nodes: int = 40, num_edges: int = 80) -> tuple[list[Node], list[Edge]]:
    """Generate a small in-memory graph for dry-run when store is empty."""
    import uuid
    nodes: list[Node] = []
    for i in range(num_nodes):
        nid = str(uuid.uuid4())
        label = f"concept_{i}" if i % 2 == 0 else f"topic: cluster_{i % 5}"
        nodes.append(
            Node(
                node_id=nid,
                label=label,
                mass=1.0,
                activation=0.0,
                state=MemoryState.DORMANT,
                position=[float(i % 7) * 0.5, float(i % 11) * 0.3, 0.0],
                velocity=[0.0, 0.0, 0.0],
            )
        )
    node_ids = [n.node_id for n in nodes]
    edges: list[Edge] = []
    rng = np.random.default_rng(42)
    for _ in range(num_edges):
        i, j = rng.integers(0, len(nodes), size=2)
        if i == j:
            j = (j + 1) % len(nodes)
        w = float(rng.uniform(0.3, 1.0))
        edges.append(
            Edge(src_id=node_ids[i], dst_id=node_ids[j], relation="relates", weight=w)
        )
    return nodes, edges


def _seed_nodes_from_labels(
    client: NebulaGraphClient,
    seed_labels: list[str],
    *,
    limit: int = 500,
) -> list[Node]:
    if not seed_labels:
        return []
    keywords = [s.strip() for s in seed_labels if s.strip()]
    if not keywords:
        return []
    nodes = client.list_nodes_by_label_keywords(keywords, limit=limit)
    return nodes


def _seed_nodes_from_ids(client: NebulaGraphClient, seed_ids: list[str]) -> list[Node]:
    if not seed_ids:
        return []
    return client.get_nodes_by_ids(seed_ids)


def _seed_nodes_from_label_keywords(
    client: NebulaGraphClient,
    seed_labels: list[str],
    limit: int = 500,
) -> list[Node]:
    keywords = [s.strip() for s in seed_labels if s.strip()]
    if not keywords:
        return []
    return client.list_nodes_by_label_keywords(keywords, limit=limit)


def _count_states(nodes: list[Node]) -> dict[str, int]:
    counts: dict[str, int] = {"active": 0, "dormant": 0, "deep": 0}
    for n in nodes:
        if n.state == MemoryState.ACTIVE:
            counts["active"] += 1
        elif n.state == MemoryState.DORMANT:
            counts["dormant"] += 1
        else:
            counts["deep"] += 1
    return counts


def _top_activated(activations: dict[str, float], n: int = 5) -> list[tuple[str, float]]:
    sorted_items = sorted(activations.items(), key=lambda x: -x[1])
    return sorted_items[:n]


def _compute_coherence_stub(nodes: list[Node]) -> float:
    """Simple coherence: mean activation of nodes with activation > threshold."""
    acts = [n.activation for n in nodes if n.activation >= SPREAD_THRESHOLD]
    if not acts:
        return 0.0
    return float(np.mean(acts))


def _compute_tension_stub(nodes: list[Node], edges: list[Edge]) -> float:
    """Stub: sum of squared distance errors for edges (ideal = 1/weight)."""
    try:
        from src.reasoning.tension import compute_tension
    except ImportError:
        return 0.0
    id_to_idx = {n.node_id: i for i, n in enumerate(nodes)}
    positions = {n.node_id: np.array(n.position, dtype=np.float32) for n in nodes}
    expected: dict[tuple[str, str], float] = {}
    for e in edges:
        if e.src_id in positions and e.dst_id in positions and e.weight > 0:
            expected[(e.src_id, e.dst_id)] = 1.0 / float(e.weight)
    if not expected:
        return 0.0
    result = compute_tension(positions, expected)
    return result.score


def _apply_gravity_step(
    nodes: list[Node],
    edges: list[Edge],
    config_path: str = "configs/simulation.yaml",
    *,
    use_faiss_approx: bool = True,
    faiss_k: int = 50,
) -> list[Node]:
    """One gravity step: build_state -> compute_forces -> update_positions; return updated nodes."""
    state = build_state(nodes, dimensions=3)
    forces = compute_forces(
        state,
        edges,
        config_path=config_path,
        use_faiss_approx=use_faiss_approx,
        faiss_k=faiss_k,
    )
    state = update_positions(state, forces, config_path=config_path, step_size=0.1)
    id_to_node = {n.node_id: n for n in nodes}
    out: list[Node] = []
    for i, nid in enumerate(state.node_ids):
        n = id_to_node[nid]
        out.append(
            replace(
                n,
                position=state.positions[i].tolist(),
                velocity=state.velocities[i].tolist(),
            )
        )
    return out


def _export_dot(
    path: str | Path,
    nodes: list[Node],
    edges: list[Edge],
    *,
    activations: dict[str, float] | None = None,
) -> None:
    """Write a Graphviz .dot file: nodes sized by activation/mass, colored by state."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    acts = activations or {n.node_id: n.activation for n in nodes}
    lines = ["digraph G {", "  rankdir=LR;", "  node [shape=circle];"]
    for n in nodes:
        a = acts.get(n.node_id, n.activation)
        m = max(0.3, n.mass)
        size = 0.5 + 0.8 * min(1.0, float(a)) + 0.2 * min(1.0, m / 5.0)
        if n.state == MemoryState.ACTIVE:
            color = "green"
        elif n.state == MemoryState.DORMANT:
            color = "gold"
        else:
            color = "gray"
        label = n.label.replace('"', '\\"')[:30]
        lines.append(f'  "{n.node_id}" [label="{label}", width={size:.2f}, color={color}];')
    for e in edges:
        if e.relation != "relates":
            continue
        w = max(0.1, e.weight)
        lines.append(f'  "{e.src_id}" -> "{e.dst_id}" [weight={w:.2f}];')
    lines.append("}")
    path.write_text("\n".join(lines), encoding="utf-8")


def run_demo(
    client: NebulaGraphClient,
    *,
    seed_ids: list[str],
    seed_labels: list[str],
    ticks: int = DEFAULT_TICKS,
    decay_rate: float = DEFAULT_DECAY_RATE,
    enable_forces: bool = False,
    export_dot_path: str | Path | None = None,
    verbose: bool = False,
    graph_space: str | None = None,
    config_path: str = "configs/graph.yaml",
    simulation_config_path: str = "configs/simulation.yaml",
) -> tuple[list[Node], list[Edge], dict]:
    """
    Run the cognition tick loop. Returns (final nodes, edges, summary dict).
    Raises on any failure (no silent fallbacks).
    """
    if graph_space is not None and not client.dry_run:
        # Override space: re-init or execute USE
        try:
            client._session.execute(f"USE {graph_space};")
        except Exception as e:
            raise RuntimeError(
                f"Failed to use graph space '{graph_space}'. "
                f"Check Nebula connection and space name. {e}"
            ) from e

    # Load graph: from client or synthetic for dry-run empty store
    nodes = client.list_nodes(limit=NODE_LIMIT)
    edges = client.list_edges(limit=EDGE_LIMIT)
    if not nodes and client.dry_run:
        logger.info("Dry-run store empty; generating synthetic graph.")
        syn_nodes, syn_edges = _generate_synthetic_graph(40, 80)
        client.insert_nodes(syn_nodes)
        client.insert_edges(syn_edges)
        nodes = client.list_nodes(limit=NODE_LIMIT)
        edges = client.list_edges(limit=EDGE_LIMIT)
    if not nodes:
        raise ValueError(
            "No nodes in graph. Load data or use dry_run with synthetic graph."
        )

    # Seed selection
    seed_nodes: list[Node] = []
    if seed_ids:
        seed_nodes = _seed_nodes_from_ids(client, seed_ids)
    if seed_labels and not seed_nodes:
        seed_nodes = _seed_nodes_from_label_keywords(client, seed_labels, limit=500)
    if not seed_nodes:
        raise ValueError(
            "No seed nodes matched (--seed-ids or --seed-labels). "
            "Provide at least one seed."
        )
    seed_id_list = [n.node_id for n in seed_nodes]
    # Boost seed activations to 1.0 in our working set
    seed_set = set(seed_id_list)
    nodes = [
        replace(n, activation=1.0) if n.node_id in seed_set else n
        for n in nodes
    ]

    low_activation_ticks: dict[str, int] = {}
    summary: dict = {"ticks": ticks, "seed_count": len(seed_id_list), "states_per_tick": []}

    for tick in range(ticks):
        # 1. Spreading activation (seeds re-injected each tick)
        updated_nodes, prop_result = activate_and_propagate(
            nodes,
            edges,
            seed_id_list,
            max_hops=SPREAD_MAX_HOPS,
            decay=SPREAD_DECAY,
            threshold=SPREAD_THRESHOLD,
        )
        activations = prop_result.activations

        # 2. Memory tick
        updated_nodes, low_activation_ticks = memory_tick(
            updated_nodes,
            low_activation_ticks,
            decay_rate=decay_rate,
            active_threshold=ACTIVE_THRESHOLD,
            dormant_threshold=DORMANT_THRESHOLD,
            ticks_to_deep=TICKS_TO_DEEP,
        )

        # 3. Optional forces/gravity
        if enable_forces:
            updated_nodes = _apply_gravity_step(
                updated_nodes,
                edges,
                config_path=simulation_config_path,
                use_faiss_approx=True,
                faiss_k=50,
            )

        nodes = updated_nodes

        # 4. Persist to Nebula if not dry-run
        if not client.dry_run:
            client.update_nodes(nodes)

        # 5. Metrics
        state_counts = _count_states(nodes)
        summary["states_per_tick"].append(state_counts)
        active_sub, induced_edges, _ = get_activated_subgraph(
            nodes, edges, seed_id_list, min_activation=SPREAD_THRESHOLD, max_hops=SPREAD_MAX_HOPS, decay=SPREAD_DECAY
        )
        coherence = _compute_coherence_stub(active_sub)
        tension = _compute_tension_stub(nodes, edges)

        if verbose:
            top = _top_activated(activations, n=5)
            top_str = ", ".join(f"{nid[:8]}={a:.3f}" for nid, a in top)
            logger.info(
                "Tick %d/%d: active=%d dormant=%d deep=%d | top=%s | coherence=%.4f tension=%.4f",
                tick + 1,
                ticks,
                state_counts["active"],
                state_counts["dormant"],
                state_counts["deep"],
                top_str,
                coherence,
                tension,
            )
        else:
            print(
                f"Tick {tick + 1}/{ticks}: "
                f"ACTIVE={state_counts['active']} DORMANT={state_counts['dormant']} DEEP={state_counts['deep']} "
                f"| coherence={coherence:.4f} tension={tension:.4f}"
            )
            top = _top_activated(activations, n=5)
            print(f"  Top activated: {[(nid[:12] + '…', round(a, 3)) for nid, a in top]}")

        # 6. Export DOT (final tick only)
        if export_dot_path and (tick == ticks - 1):
            p = Path(export_dot_path)
            out_path = p if p.suffix == ".dot" else Path(str(p) + ".dot")
            _export_dot(out_path, nodes, edges, activations=activations)

    summary["final_states"] = _count_states(nodes)
    return nodes, edges, summary


def main() -> int:
    _ensure_agi_loop_deps()
    parser = argparse.ArgumentParser(
        description="Run a minimal TS cognition cycle: activation spread, memory tick, optional gravity."
    )
    parser.add_argument(
        "--graph-space",
        type=str,
        default=None,
        help="Nebula space name (default from config).",
    )
    parser.add_argument(
        "--seed-labels",
        type=str,
        default="",
        help="Comma-separated label keywords, e.g. apple,fruit.",
    )
    parser.add_argument(
        "--seed-ids",
        type=str,
        default="",
        help="Comma-separated node IDs for seeds.",
    )
    parser.add_argument(
        "--ticks",
        type=int,
        default=DEFAULT_TICKS,
        help=f"Number of simulation ticks (default {DEFAULT_TICKS}).",
    )
    parser.add_argument(
        "--decay-rate",
        type=float,
        default=DEFAULT_DECAY_RATE,
        help=f"Memory decay per tick (default {DEFAULT_DECAY_RATE}).",
    )
    parser.add_argument(
        "--enable-forces",
        action="store_true",
        help="Run gravity step each tick.",
    )
    parser.add_argument(
        "--export-dot",
        type=str,
        default=None,
        metavar="PATH",
        help="Export Graphviz .dot file (final or per-tick).",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="More logging.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Use in-memory store (no Nebula). Synthetic graph if empty.",
    )
    parser.add_argument(
        "--config",
        type=str,
        default="configs/graph.yaml",
        help="Graph config path.",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s:%(name)s:%(message)s",
    )

    seed_ids = [s.strip() for s in args.seed_ids.split(",") if s.strip()]
    seed_labels = [s.strip() for s in args.seed_labels.split(",") if s.strip()]
    if not seed_ids and not seed_labels:
        # Default seeds for dry-run: use first few concept nodes
        if args.dry_run:
            seed_labels = ["concept"]  # synthetic labels include "concept_0", etc.
        else:
            print("Error: provide --seed-ids or --seed-labels.", file=sys.stderr)
            return 1

    try:
        client = NebulaGraphClient(config_path=args.config, dry_run_override=args.dry_run)
    except Exception as e:
        raise ConnectionError(
            f"NebulaGraph client init failed. Use --dry-run for in-memory. {e}"
        ) from e

    try:
        nodes, edges, summary = run_demo(
            client,
            seed_ids=seed_ids,
            seed_labels=seed_labels,
            ticks=args.ticks,
            decay_rate=args.decay_rate,
            enable_forces=args.enable_forces,
            export_dot_path=args.export_dot,
            verbose=args.verbose,
            graph_space=args.graph_space,
            config_path=args.config,
        )
    except Exception as e:
        logger.exception("Demo failed")
        print(f"Error: {e}", file=sys.stderr)
        return 1
    finally:
        client.close()

    print(
        f"Done. Ticks={summary['ticks']}, Seeds={summary['seed_count']}, "
        f"Final ACTIVE={summary['final_states']['active']} DORMANT={summary['final_states']['dormant']} DEEP={summary['final_states']['deep']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
