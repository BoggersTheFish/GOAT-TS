"""
Stage 4: Streamlit visualization for cognition graph and demo loop.
Run from repo root: streamlit run scripts/streamlit_viz.py
Requires: pip install streamlit
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> None:
    try:
        import streamlit as st
    except ImportError:
        print("Streamlit is required. Install with: pip install streamlit", file=sys.stderr)
        sys.exit(1)

    st.set_page_config(page_title="GOAT Cognition Viz", layout="wide")
    st.title("GOAT-TS Cognition Visualization")

    st.sidebar.header("Mode")
    mode = st.sidebar.radio("Choose", ["Demo summary", "Graph stats (dry-run)"], index=0)

    if mode == "Demo summary":
        st.subheader("Run a short cognition demo (dry-run)")
        ticks = st.sidebar.slider("Ticks", 1, 20, 5)
        if st.sidebar.button("Run demo"):
            from src.agi_loop.demo_loop import run_demo
            from src.graph.client import NebulaGraphClient
            config_path = str(ROOT / "configs" / "graph.yaml")
            client = NebulaGraphClient(config_path=config_path, dry_run_override=True)
            try:
                nodes, edges, summary = run_demo(
                    client,
                    seed_ids=[],
                    seed_labels=["concept"],
                    ticks=ticks,
                    verbose=False,
                    config_path=config_path,
                )
            finally:
                client.close()
            st.write("**Summary**")
            st.json({
                "ticks": summary["ticks"],
                "seed_count": summary["seed_count"],
                "final_states": summary.get("final_states", {}),
                "node_count": len(nodes),
                "edge_count": len(edges),
            })
            if summary.get("states_per_tick"):
                st.line_chart(
                    {f"tick_{i}": s.get("active", 0) for i, s in enumerate(summary["states_per_tick"])}
                )
        else:
            st.info("Click **Run demo** in the sidebar to execute a dry-run cognition loop.")

    else:
        st.subheader("Graph stats (dry-run snapshot)")
        from src.graph.client import NebulaGraphClient
        config_path = str(ROOT / "configs" / "graph.yaml")
        client = NebulaGraphClient(config_path=config_path, dry_run_override=True)
        try:
            nodes = client.list_nodes(limit=500)
            edges = client.list_edges(limit=1000)
        finally:
            client.close()
        st.metric("Nodes", len(nodes))
        st.metric("Edges", len(edges))
        if nodes:
            st.write("Sample labels")
            st.table([{"node_id": n.node_id[:20], "label": n.label[:40], "activation": round(n.activation, 3)} for n in nodes[:15]])


if __name__ == "__main__":
    main()
