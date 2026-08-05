#!/usr/bin/env bash
# Roll out GHCR images on a host that already has docker compose prod files.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
ENV_FILE="${ENV_FILE:-$ROOT_DIR/.env.production}"
COMPOSE_FILE="${COMPOSE_FILE:-$ROOT_DIR/docker-compose.prod.yml}"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing env file: $ENV_FILE" >&2
  exit 1
fi

echo "Pulling images..."
docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" pull

echo "Restarting stack..."
docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" up -d

echo "Waiting for health..."
sleep 5
curl -fsS "${HEALTH_URL:-http://localhost:8000/health}" | tee /dev/stderr
echo
curl -fsS "${READY_URL:-http://localhost:8000/ready}" | tee /dev/stderr || true
echo
echo "Deploy complete."
