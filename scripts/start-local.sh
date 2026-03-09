#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="${ROOT_DIR}/docker/docker-compose.yml"

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker is not installed or not on PATH. Start Docker Desktop and verify 'docker --version' works." >&2
  exit 1
fi

echo "Starting local TS services from ${COMPOSE_FILE}"
if ! docker compose -f "${COMPOSE_FILE}" up -d; then
  echo "docker compose failed. Review the output above for the failing service or image." >&2
  exit 1
fi

echo "Expected local ports:"
echo "  NebulaGraph graphd: 9669"
echo "  NebulaGraph metad: 9559"
echo "  NebulaGraph storaged: 9779"
echo "  Redis: 6379"
echo "  Spark UI: 8080"
