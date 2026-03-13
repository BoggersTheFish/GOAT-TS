from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram


query_latency_seconds = Histogram(
    "ts_query_latency_seconds",
    "Latency of reasoning loop queries.",
)

graph_node_count = Gauge(
    "ts_graph_node_count",
    "Current graph node count.",
)

graph_edge_count = Gauge(
    "ts_graph_edge_count",
    "Current graph edge count.",
)

simulation_steps_total = Counter(
    "ts_simulation_steps_total",
    "Total number of cognition/simulation steps executed.",
)

activation_coherence = Gauge(
    "ts_activation_coherence",
    "Current average activation coherence for the active subgraph.",
)

tension_score = Gauge(
    "ts_tension_score",
    "Current global tension score for the graph or subgraph.",
)

# Stage 8: efficiency
ticks_per_second = Gauge(
    "ts_ticks_per_second",
    "Cognition loop throughput (ticks per second) from last run.",
)
graph_size_nodes = Gauge(
    "ts_graph_size_nodes",
    "Total graph node count (for scale metrics).",
)
