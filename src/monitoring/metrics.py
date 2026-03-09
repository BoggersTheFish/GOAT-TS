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
    "Total number of simulation steps executed.",
)
