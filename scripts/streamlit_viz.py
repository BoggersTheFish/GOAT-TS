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
    mode = st.sidebar.radio("Choose", ["Demo summary", "Graph stats (dry-run)", "Interactive graph"], index=0)

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

    elif mode == "Graph stats (dry-run)":
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

    else:
        st.subheader("Interactive cognition graph (dry-run snapshot)")
        from src.graph.client import NebulaGraphClient

        try:
            import networkx as nx
            import plotly.graph_objects as go
        except ImportError:
            st.error("Interactive graph requires networkx and plotly. Install with: pip install networkx plotly")
            return

        config_path = str(ROOT / "configs" / "graph.yaml")
        client = NebulaGraphClient(config_path=config_path, dry_run_override=True)
        try:
            nodes = client.list_nodes(limit=300)
            edges = client.list_edges(limit=1000)
        finally:
            client.close()

        if not nodes:
            st.info("No nodes available in dry-run store yet. Run a demo loop first.")
            return

        G = nx.Graph()
        for n in nodes:
            G.add_node(
                n.node_id,
                label=n.label,
                activation=float(n.activation),
            )
        for e in edges:
            G.add_edge(e.src_id, e.dst_id, weight=float(e.weight))

        pos = nx.spring_layout(G, seed=42, k=0.25, iterations=40)
        x_nodes = [pos[n][0] for n in G.nodes()]
        y_nodes = [pos[n][1] for n in G.nodes()]
        activations = [G.nodes[n].get("activation", 0.0) for n in G.nodes()]
        labels = [G.nodes[n].get("label", "") for n in G.nodes()]

        edge_x = []
        edge_y = []
        for src, dst in G.edges():
            edge_x.extend([pos[src][0], pos[dst][0], None])
            edge_y.extend([pos[src][1], pos[dst][1], None])

        edge_trace = go.Scatter(
            x=edge_x,
            y=edge_y,
            mode="lines",
            line=dict(width=0.5, color="#AAAAAA"),
            hoverinfo="none",
        )

        node_trace = go.Scatter(
            x=x_nodes,
            y=y_nodes,
            mode="markers",
            marker=dict(
                showscale=True,
                colorscale="Viridis",
                reversescale=True,
                color=activations,
                size=10,
                colorbar=dict(
                    thickness=15,
                    title="Activation",
                    xanchor="left",
                    titleside="right",
                ),
                line_width=1,
            ),
            text=[f"{label}" for label in labels],
            hovertemplate="Label: %{text}<br>Activation: %{marker.color:.3f}<extra></extra>",
        )

        fig = go.Figure(data=[edge_trace, node_trace])
        fig.update_layout(
            showlegend=False,
            margin=dict(l=10, r=10, t=10, b=10),
            xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
            yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        )
        st.plotly_chart(fig, use_container_width=True)


if __name__ == "__main__":
    main()
