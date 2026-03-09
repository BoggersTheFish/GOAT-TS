from __future__ import annotations

import json
import logging
import os
import sqlite3
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable, Iterable

from src.graph.models import Edge, MemoryState, Node, NodeType, Wave
from src.utils import load_yaml_config

logger = logging.getLogger(__name__)


def _apply_graph_env_overrides(config: dict[str, Any], config_path: Path) -> None:
    """Load .env from repo root and override graph host/port/username/password if set."""
    try:
        from dotenv import load_dotenv
        resolved = Path(config_path).resolve()
        root = resolved.parents[1] if "configs" in resolved.parts else resolved.parent
        load_dotenv(root / ".env")
    except ImportError:
        return
    if os.getenv("NEBULA_HOST"):
        config["host"] = os.getenv("NEBULA_HOST")
    if os.getenv("NEBULA_PORT"):
        try:
            config["port"] = int(os.getenv("NEBULA_PORT", ""))
        except ValueError:
            pass
    if os.getenv("NEBULA_USERNAME"):
        config["username"] = os.getenv("NEBULA_USERNAME")
    if os.getenv("NEBULA_PASSWORD"):
        config["password"] = os.getenv("NEBULA_PASSWORD")


def _node_to_sqlite_dict(n: Node) -> dict[str, Any]:
    d = asdict(n)
    d["state"] = n.state.value
    d["node_type"] = n.node_type.value
    return d


def _node_from_sqlite_dict(d: dict[str, Any]) -> Node:
    d = dict(d)
    d["state"] = MemoryState(str(d.get("state", "dormant")))
    d["node_type"] = NodeType(str(d.get("node_type", "knowledge")))
    return Node(**d)


class InMemoryGraphStore:
    """Fallback graph store used for tests and dry-run workflows. Optional SQLite persistence."""

    def __init__(self, sqlite_path: str | Path | None = None) -> None:
        self.nodes: dict[str, Node] = {}
        self.edges: list[Edge] = []
        self.waves: dict[str, Wave] = {}
        self._sqlite_path: Path | None = Path(sqlite_path) if sqlite_path else None
        if self._sqlite_path:
            self._load_sqlite()

    def _load_sqlite(self) -> None:
        if not self._sqlite_path or not self._sqlite_path.exists():
            return
        try:
            conn = sqlite3.connect(self._sqlite_path)
            cur = conn.cursor()
            cur.execute("SELECT node_id, data FROM nodes")
            for row in cur.fetchall():
                nid, data = row[0], json.loads(row[1])
                self.nodes[nid] = _node_from_sqlite_dict(data)
            cur.execute("SELECT src_id, dst_id, relation, weight, metadata FROM edges")
            for row in cur.fetchall():
                meta = json.loads(row[4]) if row[4] else {}
                self.edges.append(Edge(src_id=row[0], dst_id=row[1], relation=row[2], weight=float(row[3]), metadata=meta))
            cur.execute("SELECT wave_id, data FROM waves")
            for row in cur.fetchall():
                wid, data = row[0], json.loads(row[1])
                self.waves[wid] = Wave(**data)
            conn.close()
        except Exception as e:
            logger.warning("Failed to load in-memory store from SQLite %s: %s", self._sqlite_path, e)

    def _save_sqlite(self) -> None:
        if not self._sqlite_path:
            return
        try:
            self._sqlite_path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(self._sqlite_path)
            cur = conn.cursor()
            cur.execute(
                "CREATE TABLE IF NOT EXISTS nodes (node_id TEXT PRIMARY KEY, data TEXT)"
            )
            cur.execute(
                "CREATE TABLE IF NOT EXISTS edges (src_id TEXT, dst_id TEXT, relation TEXT, weight REAL, metadata TEXT)"
            )
            cur.execute(
                "CREATE TABLE IF NOT EXISTS waves (wave_id TEXT PRIMARY KEY, data TEXT)"
            )
            cur.execute("DELETE FROM nodes")
            cur.execute("DELETE FROM edges")
            cur.execute("DELETE FROM waves")
            for nid, node in self.nodes.items():
                cur.execute("INSERT INTO nodes (node_id, data) VALUES (?, ?)", (nid, json.dumps(_node_to_sqlite_dict(node))))
            for e in self.edges:
                cur.execute(
                    "INSERT INTO edges (src_id, dst_id, relation, weight, metadata) VALUES (?, ?, ?, ?, ?)",
                    (e.src_id, e.dst_id, e.relation, float(e.weight), json.dumps(e.metadata)),
                )
            for wid, wave in self.waves.items():
                cur.execute("INSERT INTO waves (wave_id, data) VALUES (?, ?)", (wid, json.dumps(asdict(wave))))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning("Failed to save in-memory store to SQLite %s: %s", self._sqlite_path, e)

    def insert_nodes(self, nodes: Iterable[Node]) -> None:
        for node in nodes:
            self.nodes[node.node_id] = node
        self._save_sqlite()

    def insert_edges(self, edges: Iterable[Edge]) -> None:
        self.edges.extend(edges)
        self._save_sqlite()

    def update_edges(self, edges: Iterable[Edge]) -> None:
        """Update weight of relates edges in place (by src_id, dst_id)."""
        updates = {(e.src_id, e.dst_id): e for e in edges if e.relation == "relates"}
        new_edges: list[Edge] = []
        for e in self.edges:
            if e.relation == "relates" and (e.src_id, e.dst_id) in updates:
                new_edges.append(updates[(e.src_id, e.dst_id)])
            else:
                new_edges.append(e)
        self.edges = new_edges
        self._save_sqlite()

    def insert_waves(self, waves: Iterable[Wave]) -> None:
        for w in waves:
            self.waves[w.wave_id] = w
        self._save_sqlite()

    def get_node(self, node_id: str) -> Node | None:
        return self.nodes.get(node_id)

    def get_wave(self, wave_id: str) -> Wave | None:
        return self.waves.get(wave_id)

    def neighbors(self, node_id: str) -> list[str]:
        return [edge.dst_id for edge in self.edges if edge.src_id == node_id and edge.relation == "relates"]

    def search_by_state(self, state: str) -> list[Node]:
        return [node for node in self.nodes.values() if node.state.value == state]

    def snapshot(self) -> dict[str, Any]:
        relates_edges = [e for e in self.edges if e.relation == "relates"]
        return {
            "nodes": [asdict(node) for node in self.nodes.values()],
            "edges": [asdict(edge) for edge in relates_edges],
        }


class NebulaGraphClient:
    """Config-backed client with a dry-run in-memory fallback."""

    def __init__(
        self,
        config_path: str | Path = "configs/graph.yaml",
        dry_run_override: bool | None = None,
    ) -> None:
        path = Path(config_path)
        self.config = load_yaml_config(path)["graph"].copy()
        _apply_graph_env_overrides(self.config, path.parents[1] if "configs" in path.parts else path.parent)
        if dry_run_override is not None:
            self.config["dry_run"] = dry_run_override
        sqlite_path = self.config.get("sqlite_path")
        self._store = InMemoryGraphStore(sqlite_path=sqlite_path)
        self._pool = None
        self._session = None

        if not self.config.get("dry_run", True):
            self._connect()

    def _connect(self) -> None:
        try:
            from nebula3.Config import Config
            from nebula3.gclient.net import ConnectionPool
        except ImportError as exc:
            raise RuntimeError(
                "NebulaGraph client dependencies are not installed. "
                "Install requirements.txt or enable dry_run mode."
            ) from exc

        config = Config()
        config.max_connection_pool_size = 10
        pool = ConnectionPool()
        ok = pool.init([(self.config["host"], self.config["port"])], config)
        if not ok:
            raise RuntimeError("Failed to initialize NebulaGraph connection pool.")

        self._pool = pool
        self._session = pool.get_session(
            self.config["username"], self.config["password"]
        )
        self._session.execute(f"USE {self.config['space']};")

    @property
    def dry_run(self) -> bool:
        return bool(self.config.get("dry_run", True))

    def close(self) -> None:
        if self._session is not None:
            self._session.release()
        if self._pool is not None:
            self._pool.close()

    @staticmethod
    def _escape_nGQL_string(s: str) -> str:
        """Escape a string for use inside double-quoted nGQL string literal (backslash and quote)."""
        return str(s).replace("\\", "\\\\").replace('"', '\\"')

    def _execute(self, statement: str) -> Any:
        result = self._session.execute(statement)
        if not result.is_succeeded():
            raise RuntimeError(f"Nebula query failed: {statement}\n{result.error_msg()}")
        return result

    @staticmethod
    def _value_to_python(value: Any) -> Any:
        for accessor in ("as_string", "as_double", "as_int", "as_bool"):
            if hasattr(value, accessor):
                try:
                    return getattr(value, accessor)()
                except Exception:
                    continue
        raw = str(value)
        if raw.startswith('"') and raw.endswith('"'):
            return raw[1:-1]
        if raw == "__NULL__":
            return None
        if raw in {"true", "false"}:
            return raw == "true"
        try:
            if "." in raw:
                return float(raw)
            return int(raw)
        except ValueError:
            return raw

    @staticmethod
    def _serialize_metadata(metadata: dict[str, Any] | None) -> str:
        return json.dumps(metadata or {}, ensure_ascii=True, sort_keys=True)

    @staticmethod
    def _parse_metadata(raw: Any) -> dict[str, Any]:
        if raw in (None, "", "__NULL__"):
            return {}
        if isinstance(raw, dict):
            return raw
        try:
            parsed = json.loads(str(raw))
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}

    def _node_from_values(
        self,
        *,
        node_id: str,
        label: Any,
        mass: Any,
        activation: Any,
        state: Any,
        cluster_id: Any,
        metadata: Any = None,
    ) -> Node:
        metadata_dict = self._parse_metadata(self._value_to_python(metadata))
        return Node(
            node_id=str(node_id),
            label=str(self._value_to_python(label) or ""),
            mass=float(self._value_to_python(mass) or 0.0),
            activation=float(self._value_to_python(activation) or 0.0),
            state=MemoryState(str(self._value_to_python(state) or MemoryState.DORMANT.value)),
            cluster_id=((self._value_to_python(cluster_id) or None) and str(self._value_to_python(cluster_id))),
            metadata=metadata_dict,
            embedding=metadata_dict.get("embedding"),
            position=list(metadata_dict.get("position", [0.0, 0.0, 0.0])),
            velocity=list(metadata_dict.get("velocity", [0.0, 0.0, 0.0])),
            created_at=str(metadata_dict.get("created_at", "")) or Node(node_id="tmp", label="tmp").created_at,
            attention_weight=float(metadata_dict.get("attention_weight", 0.0) or 0.0),
        )

    def query_ngql(self, statement: str) -> Any:
        if self.dry_run:
            return {"dry_run": True, "statement": statement}
        return self._session.execute(statement)

    def insert_waves(
        self,
        waves: Iterable[Wave],
        *,
        on_progress: Callable[[int, int], None] | None = None,
        progress_interval: int = 1000,
    ) -> None:
        materialized = list(waves)
        if self.dry_run:
            self._store.insert_waves(materialized)
            if on_progress:
                on_progress(len(materialized), len(materialized))
            return

        total = len(materialized)
        for i, wave in enumerate(materialized):
            props = wave.to_properties()
            label = self._escape_nGQL_string(props["label"])
            source = self._escape_nGQL_string(props["source"])
            source_chunk_id = self._escape_nGQL_string(props["source_chunk_id"])
            statement = (
                "INSERT VERTEX wave(label, source, intensity, coherence, tension, source_chunk_id) "
                f'VALUES "{wave.wave_id}":('
                f'"{label}", "{source}", {props["intensity"]}, {props["coherence"]}, '
                f'{props["tension"]}, "{source_chunk_id}");'
            )
            self._execute(statement)
            n = i + 1
            if on_progress and (n % progress_interval == 0 or n == total):
                on_progress(n, total)

    def insert_nodes(
        self,
        nodes: Iterable[Node],
        *,
        on_progress: Callable[[int, int], None] | None = None,
        progress_interval: int = 1000,
    ) -> None:
        materialized = list(nodes)
        if self.dry_run:
            self._store.insert_nodes(materialized)
            if on_progress:
                on_progress(len(materialized), len(materialized))
            return

        total = len(materialized)
        for i, node in enumerate(materialized):
            props = node.to_properties()
            label = self._escape_nGQL_string(props["label"])
            state = self._escape_nGQL_string(props["state"])
            cluster_id = self._escape_nGQL_string(props["cluster_id"])
            metadata = self._escape_nGQL_string(self._serialize_metadata(props.get("metadata", {})))
            statement = (
                "INSERT VERTEX node(label, mass, activation, state, cluster_id, metadata) "
                f'VALUES "{node.node_id}":('
                f'"{label}", {props["mass"]}, {props["activation"]}, '
                f'"{state}", "{cluster_id}", "{metadata}");'
            )
            self._execute(statement)
            n = i + 1
            if on_progress and (n % progress_interval == 0 or n == total):
                on_progress(n, total)

    def insert_edges(
        self,
        edges: Iterable[Edge],
        *,
        on_progress: Callable[[int, int], None] | None = None,
        progress_interval: int = 1000,
    ) -> None:
        materialized = list(edges)
        if self.dry_run:
            self._store.insert_edges(materialized)
            if on_progress:
                on_progress(len(materialized), len(materialized))
            return

        total = len(materialized)
        for i, edge in enumerate(materialized):
            props = edge.to_properties()
            statement = (
                f'INSERT EDGE {edge.relation}(weight) VALUES "{edge.src_id}"'
                f'->"{edge.dst_id}":({props["weight"]});'
            )
            self._execute(statement)
            n = i + 1
            if on_progress and (n % progress_interval == 0 or n == total):
                on_progress(n, total)

    def update_edges(
        self,
        edges: Iterable[Edge],
        *,
        on_progress: Callable[[int, int], None] | None = None,
        progress_interval: int = 500,
    ) -> None:
        """Update edge weights (e.g. after learning feedback). Only relates edges are updated."""
        materialized = [e for e in edges if e.relation == "relates"]
        if self.dry_run:
            self._store.update_edges(materialized)
            if on_progress:
                on_progress(len(materialized), len(materialized))
            return

        total = len(materialized)
        for i, edge in enumerate(materialized):
            src_esc = self._escape_nGQL_string(edge.src_id)
            dst_esc = self._escape_nGQL_string(edge.dst_id)
            statement = (
                f'UPDATE EDGE ON relates "{src_esc}" -> "{dst_esc}" '
                f'SET weight = {float(edge.weight)};'
            )
            self._execute(statement)
            n = i + 1
            if on_progress and (n % progress_interval == 0 or n == total):
                on_progress(n, total)

    def update_nodes(
        self,
        nodes: Iterable[Node],
        *,
        domain_map: dict[str, int] | None = None,
        on_progress: Callable[[int, int], None] | None = None,
        progress_interval: int = 500,
    ) -> None:
        """Persist node mass, activation, state, and cluster_id (or domain) to the graph."""
        materialized = list(nodes)
        if self.dry_run:
            for node in materialized:
                self._store.nodes[node.node_id] = node
            if on_progress:
                on_progress(len(materialized), len(materialized))
            return

        total = len(materialized)
        for i, node in enumerate(materialized):
            cluster_id = (
                f"domain_{domain_map[node.node_id]}"
                if domain_map and node.node_id in domain_map
                else (node.cluster_id or "")
            )
            state = self._escape_nGQL_string(node.state.value)
            cid = self._escape_nGQL_string(cluster_id)
            nid_esc = self._escape_nGQL_string(node.node_id)
            metadata = self._escape_nGQL_string(self._serialize_metadata(node.to_properties().get("metadata", {})))
            statement = (
                f'UPDATE VERTEX ON node "{nid_esc}" '
                f'SET mass = {node.mass}, activation = {node.activation}, '
                f'state = "{state}", cluster_id = "{cid}", metadata = "{metadata}";'
            )
            self._execute(statement)
            n = i + 1
            if on_progress and (n % progress_interval == 0 or n == total):
                on_progress(n, total)

    def backup_snapshot(self, path: str | Path, *, node_limit: int = 10000, edge_limit: int = 50000) -> None:
        """Write a graph backup (nodes, relates edges, waves) to a JSON file for versioning/restore."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        if self.dry_run:
            snapshot = self._store.snapshot()
            waves = [asdict(w) for w in self._store.waves.values()]
        else:
            nodes = self.list_nodes(limit=node_limit)
            edges = self.list_edges(limit=edge_limit)
            waves_list = self.list_waves(limit=2000)
            snapshot = {"nodes": [asdict(n) for n in nodes], "edges": [asdict(e) for e in edges]}
            waves = [asdict(w) for w in waves_list]
        payload = {"nodes": snapshot["nodes"], "edges": snapshot["edges"], "waves": waves}
        path.write_text(json.dumps(payload, indent=0, default=str), encoding="utf-8")
        logger.info("Backup snapshot written to %s (%s nodes, %s edges, %s waves).",
                    path, len(snapshot["nodes"]), len(snapshot["edges"]), len(waves))

    def get_node(self, node_id: str) -> Node | None:
        if self.dry_run:
            return self._store.get_node(node_id)

        result = self._execute(
            f'FETCH PROP ON node "{node_id}" YIELD properties(vertex).label AS label, '
            "properties(vertex).mass AS mass, properties(vertex).activation AS activation, "
            "properties(vertex).state AS state, properties(vertex).cluster_id AS cluster_id, properties(vertex).metadata AS metadata;"
        )
        if result.row_size() == 0:
            return None

        row = result.row_values(0)
        return self._node_from_values(
            node_id=node_id,
            label=row[0],
            mass=row[1],
            activation=row[2],
            state=row[3],
            cluster_id=row[4],
            metadata=row[5],
        )

    def get_wave(self, wave_id: str) -> Wave | None:
        if self.dry_run:
            return self._store.get_wave(wave_id)

        try:
            result = self._execute(
                f'FETCH PROP ON wave "{self._escape_nGQL_string(wave_id)}" '
                "YIELD properties(vertex).label AS label, properties(vertex).source AS source, "
                "properties(vertex).intensity AS intensity, properties(vertex).coherence AS coherence, "
                "properties(vertex).tension AS tension, properties(vertex).source_chunk_id AS source_chunk_id;"
            )
        except Exception:
            return None
        if result.row_size() == 0:
            return None
        row = result.row_values(0)
        return Wave(
            wave_id=wave_id,
            label=row[0].as_string(),
            source=row[1].as_string(),
            intensity=row[2].as_double(),
            coherence=row[3].as_double(),
            tension=row[4].as_double(),
            source_chunk_id=row[5].as_string(),
        )

    def list_waves(self, limit: int = 500, source: str | None = None) -> list[Wave]:
        if self.dry_run:
            waves = list(self._store.waves.values())
            if source is not None:
                waves = [w for w in waves if w.source == source]
            return waves[:limit]

        source_cond = f' AND properties(v).source == "{self._escape_nGQL_string(source)}"' if source else ""
        try:
            result = self._execute(
                "MATCH (v:wave) "
                f"WHERE 1{source_cond} "
                "RETURN id(v) AS wave_id, properties(v).label AS label, properties(v).source AS source, "
                "properties(v).intensity AS intensity, properties(v).coherence AS coherence, "
                "properties(v).tension AS tension, properties(v).source_chunk_id AS source_chunk_id "
                f"LIMIT {limit};"
            )
        except Exception:
            return []
        out: list[Wave] = []
        for idx in range(result.row_size()):
            row = result.row_values(idx)
            out.append(
                Wave(
                    wave_id=str(self._value_to_python(row[0])),
                    label=str(self._value_to_python(row[1]) or ""),
                    source=str(self._value_to_python(row[2]) or ""),
                    intensity=float(self._value_to_python(row[3]) or 0.0),
                    coherence=float(self._value_to_python(row[4]) or 0.0),
                    tension=float(self._value_to_python(row[5]) or 0.0),
                    source_chunk_id=str(self._value_to_python(row[6]) or ""),
                )
            )
        return out

    def list_in_wave_edges(self, wave_id: str | None = None, limit: int = 5000) -> list[Edge]:
        """Return concept->wave edges (in_wave). Optionally filter by wave_id."""
        if self.dry_run:
            in_wave = [e for e in self._store.edges if e.relation == "in_wave"]
            if wave_id is not None:
                in_wave = [e for e in in_wave if e.dst_id == wave_id]
            return in_wave[:limit]

        wave_cond = f' AND id(dst) == "{self._escape_nGQL_string(wave_id)}"' if wave_id else ""
        try:
            result = self._execute(
                "MATCH (src:node)-[e:in_wave]->(dst:wave) "
                f"WHERE 1{wave_cond} "
                "RETURN id(src) AS src_id, id(dst) AS dst_id, properties(e).weight AS weight "
                f"LIMIT {limit};"
            )
        except Exception:
            return []
        return [
            Edge(
                src_id=str(self._value_to_python(row[0])),
                dst_id=str(self._value_to_python(row[1])),
                relation="in_wave",
                weight=float(self._value_to_python(row[2]) or 0.0),
            )
            for idx in range(result.row_size())
            for row in [result.row_values(idx)]
        ]

    def neighbors(self, node_id: str) -> list[str]:
        if self.dry_run:
            return self._store.neighbors(node_id)

        result = self._execute(
            f'GO FROM "{node_id}" OVER relates YIELD dst(edge) AS neighbor;'
        )
        return [result.row_values(idx)[0].as_string() for idx in range(result.row_size())]

    def search_by_state(self, state: str) -> list[Node]:
        if self.dry_run:
            return self._store.search_by_state(state)

        result = self._execute(
            "LOOKUP ON node "
            f'WHERE node.state == "{state}" '
            "YIELD id(vertex) AS node_id, properties(vertex).label AS label, "
            "properties(vertex).mass AS mass, properties(vertex).activation AS activation, "
            "properties(vertex).state AS state, properties(vertex).cluster_id AS cluster_id, properties(vertex).metadata AS metadata;"
        )

        nodes: list[Node] = []
        for idx in range(result.row_size()):
            row = result.row_values(idx)
            nodes.append(
                self._node_from_values(
                    node_id=str(self._value_to_python(row[0])),
                    label=row[1],
                    mass=row[2],
                    activation=row[3],
                    state=row[4],
                    cluster_id=row[5],
                    metadata=row[6],
                )
            )
        return nodes

    def list_cluster_nodes(self, limit: int = 200) -> list[Node]:
        """Return topic/cluster nodes (label starts with 'topic: '). Used for query-context retrieval."""
        if self.dry_run:
            out = [
                n for n in self._store.nodes.values()
                if n.label.startswith("topic:")
            ][:limit]
            return out
        try:
            result = self._execute(
                'MATCH (v:node) WHERE lower(properties(v).label) STARTS WITH "topic: " '
                "RETURN id(v) AS node_id, properties(v).label AS label, properties(v).mass AS mass, "
                "properties(v).activation AS activation, properties(v).state AS state, properties(v).cluster_id AS cluster_id, properties(v).metadata AS metadata "
                f"LIMIT {limit};"
            )
        except Exception:
            return []
        nodes = []
        for idx in range(result.row_size()):
            row = result.row_values(idx)
            nodes.append(
                self._node_from_values(
                    node_id=str(self._value_to_python(row[0])),
                    label=row[1],
                    mass=row[2],
                    activation=row[3],
                    state=row[4],
                    cluster_id=row[5],
                    metadata=row[6],
                )
            )
        return nodes

    def list_nodes_by_label_keywords(
        self,
        keywords: list[str],
        limit: int = 500,
        *,
        cluster_ids: list[str] | None = None,
    ) -> list[Node]:
        """Return nodes whose label contains any keyword (case-insensitive). Optionally restrict to cluster_ids."""
        if not keywords:
            return self.list_nodes(limit=limit)
        terms = [k.strip().lower() for k in keywords if k and len(k.strip()) >= 2]
        if not terms:
            return self.list_nodes(limit=limit)

        if self.dry_run:
            out: list[Node] = []
            lower_labels = {tid: n.label.lower() for tid, n in self._store.nodes.items()}
            for nid, node in self._store.nodes.items():
                if len(out) >= limit:
                    break
                lab = lower_labels[nid]
                if any(t in lab for t in terms):
                    if cluster_ids is not None and (node.cluster_id or "") not in cluster_ids:
                        continue
                    out.append(node)
            return out

        escaped = [self._escape_nGQL_string(t) for t in terms]
        label_conds = " OR ".join(
            f'lower(properties(v).label) CONTAINS "{e}"' for e in escaped
        )
        cluster_cond = ""
        if cluster_ids:
            esc_ids = [self._escape_nGQL_string(cid) for cid in cluster_ids]
            cluster_cond = " AND (" + " OR ".join(
                f'properties(v).cluster_id == "{e}"' for e in esc_ids
            ) + ")"
        try:
            result = self._execute(
                f"MATCH (v:node) WHERE ({label_conds}){cluster_cond} "
                "RETURN id(v) AS node_id, properties(v).label AS label, properties(v).mass AS mass, "
                "properties(v).activation AS activation, properties(v).state AS state, properties(v).cluster_id AS cluster_id, properties(v).metadata AS metadata "
                f"LIMIT {limit};"
            )
        except Exception:
            return self.list_nodes(limit=limit)
        nodes: list[Node] = []
        for idx in range(result.row_size()):
            row = result.row_values(idx)
            nodes.append(
                self._node_from_values(
                    node_id=str(self._value_to_python(row[0])),
                    label=row[1],
                    mass=row[2],
                    activation=row[3],
                    state=row[4],
                    cluster_id=row[5],
                    metadata=row[6],
                )
            )
        return nodes

    def list_nodes(self, limit: int = 1000) -> list[Node]:
        if self.dry_run:
            return list(self._store.nodes.values())[:limit]

        result = self._execute(
            "MATCH (v:node) "
            "RETURN id(v) AS node_id, properties(v).label AS label, properties(v).mass AS mass, "
            "properties(v).activation AS activation, properties(v).state AS state, properties(v).cluster_id AS cluster_id, properties(v).metadata AS metadata "
            f"LIMIT {limit};"
        )
        nodes: list[Node] = []
        for idx in range(result.row_size()):
            row = result.row_values(idx)
            nodes.append(
                self._node_from_values(
                    node_id=str(self._value_to_python(row[0])),
                    label=row[1],
                    mass=row[2],
                    activation=row[3],
                    state=row[4],
                    cluster_id=row[5],
                    metadata=row[6],
                )
            )
        return nodes

    def list_edges(self, limit: int = 5000) -> list[Edge]:
        if self.dry_run:
            relates = [e for e in self._store.edges if e.relation == "relates"]
            return relates[:limit]

        result = self._execute(
            "MATCH (src:node)-[e:relates]->(dst:node) "
            "RETURN id(src) AS src_id, id(dst) AS dst_id, properties(e).weight AS weight "
            f"LIMIT {limit};"
        )
        edges: list[Edge] = []
        for idx in range(result.row_size()):
            row = result.row_values(idx)
            edges.append(
                Edge(
                    src_id=str(self._value_to_python(row[0])),
                    dst_id=str(self._value_to_python(row[1])),
                    relation="relates",
                    weight=float(self._value_to_python(row[2]) or 0.0),
                )
            )
        return edges

    def list_edges_between(self, node_ids: set[str] | list[str], limit: int = 5000) -> list[Edge]:
        """Return relates edges that have both endpoints in node_ids (induced subgraph edges)."""
        ids = list(node_ids)[:500] if node_ids else []
        if not ids:
            return []
        if self.dry_run:
            node_set = set(ids)
            return [
                e for e in self._store.edges
                if e.relation == "relates" and e.src_id in node_set and e.dst_id in node_set
            ][:limit]
        quoted = ", ".join(f'"{self._escape_nGQL_string(nid)}"' for nid in ids)
        result = self._execute(
            "MATCH (a:node)-[e:relates]->(b:node) "
            f"WHERE id(a) IN [{quoted}] AND id(b) IN [{quoted}] "
            "RETURN id(a) AS src_id, id(b) AS dst_id, properties(e).weight AS weight "
            f"LIMIT {limit};"
        )
        edges = []
        for idx in range(result.row_size()):
            row = result.row_values(idx)
            edges.append(
                Edge(
                    src_id=str(self._value_to_python(row[0])),
                    dst_id=str(self._value_to_python(row[1])),
                    relation="relates",
                    weight=float(self._value_to_python(row[2]) or 0.0),
                )
            )
        return edges

    def get_nodes_by_ids(self, node_ids: list[str]) -> list[Node]:
        """Fetch nodes by a list of vertex ids. Returns empty if none found or on error."""
        if not node_ids:
            return []
        if self.dry_run:
            return [self._store.nodes[nid] for nid in node_ids if nid in self._store.nodes]
        # Build IN list: ["id1", "id2", ...] with escaped ids
        quoted = ", ".join(f'"{self._escape_nGQL_string(nid)}"' for nid in node_ids[:500])
        try:
            result = self._execute(
                f"MATCH (v:node) WHERE id(v) IN [{quoted}] "
                "RETURN id(v) AS node_id, properties(v).label AS label, properties(v).mass AS mass, "
                "properties(v).activation AS activation, properties(v).state AS state, properties(v).cluster_id AS cluster_id, properties(v).metadata AS metadata;"
            )
        except Exception:
            return []
        nodes = []
        for idx in range(result.row_size()):
            row = result.row_values(idx)
            nodes.append(
                self._node_from_values(
                    node_id=str(self._value_to_python(row[0])),
                    label=row[1],
                    mass=row[2],
                    activation=row[3],
                    state=row[4],
                    cluster_id=row[5],
                    metadata=row[6],
                )
            )
        return nodes

    def snapshot_induced_by_edges(self, edge_limit: int = 500) -> dict[str, Any]:
        """Snapshot that starts from edges so the subgraph has edges (connected). Uses first edge_limit relates edges, then all concept nodes incident to them."""
        if self.dry_run:
            relates = [e for e in self._store.edges if e.relation == "relates"][:edge_limit]
            node_ids = set()
            for e in relates:
                node_ids.add(e.src_id)
                node_ids.add(e.dst_id)
            nodes = [self._store.nodes[nid] for nid in node_ids if nid in self._store.nodes]
            return {
                "nodes": [asdict(n) for n in nodes],
                "edges": [asdict(e) for e in relates],
            }
        edges = self.list_edges(limit=edge_limit)
        if not edges:
            return {"nodes": [], "edges": []}
        node_ids = list({e.src_id for e in edges} | {e.dst_id for e in edges})
        nodes = self.get_nodes_by_ids(node_ids)
        return {
            "nodes": [asdict(n) for n in nodes],
            "edges": [asdict(e) for e in edges],
        }

    def snapshot(
        self,
        node_limit: int = 1000,
        edge_limit: int = 5000,
        *,
        label_keywords: list[str] | None = None,
        cluster_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        """Build a graph snapshot. If label_keywords is set, nodes are filtered by label (query-driven).
        If cluster_ids is set, restrict to nodes in those topic clusters (call-context)."""
        if self.dry_run:
            return self._store.snapshot()

        if label_keywords:
            nodes = self.list_nodes_by_label_keywords(
                label_keywords, limit=node_limit, cluster_ids=cluster_ids
            )
        else:
            nodes = self.list_nodes(limit=node_limit)
        node_ids = {node.node_id for node in nodes}
        edges = self.list_edges_between(node_ids, limit=edge_limit)
        return {
            "nodes": [asdict(node) for node in nodes],
            "edges": [asdict(edge) for edge in edges],
        }
