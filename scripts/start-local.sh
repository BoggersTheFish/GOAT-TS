#!/usr/bin/env bash
# Start local TS stack (NebulaGraph, Redis, Spark). Use from repo root.
# macOS / Linux. For Windows use: .\scripts\start-local.ps1

set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
COMPOSE_FILE="$ROOT/docker/docker-compose.yml"

if ! command -v docker &>/dev/null; then
  echo "Docker is not installed or not on PATH. Install Docker and ensure 'docker --version' works."
  exit 1
fi

echo "Starting local TS services from $COMPOSE_FILE"
docker compose -f "$COMPOSE_FILE" up -d

echo ""
echo "Expected local ports:"
echo "  NebulaGraph graphd: 9669"
echo "  NebulaGraph metad: 9559"
echo "  NebulaGraph storaged: 9779"
echo "  Redis: 6379"
echo "  Spark UI: 8080"
