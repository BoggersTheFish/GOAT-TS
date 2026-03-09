from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.utils import load_yaml_config


class CacheAdapter:
    def __init__(self, config_path: str | Path = "configs/reasoning.yaml") -> None:
        self.config = load_yaml_config(config_path)["reasoning"]
        self._client = None

        if self.config.get("cache_enabled", False):
            try:
                import redis
            except ImportError:
                self._client = False
                return

            host = self.config.get("redis_host", "127.0.0.1")
            port = int(self.config.get("redis_port", 6379))
            self._client = redis.Redis(host=host, port=port, decode_responses=True)

    def get(self, key: str) -> Any | None:
        if self._client in (None, False):
            return None
        payload = self._client.get(key)
        return json.loads(payload) if payload else None

    def set(self, key: str, value: Any, ttl_s: int | None = None) -> None:
        if self._client in (None, False):
            return
        if ttl_s is None:
            ttl_s = int(self.config.get("cache_ttl_s", 300))
        self._client.set(key, json.dumps(value), ex=ttl_s)
