#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../../.."
COMPOSE=(docker compose -p carcraft-22296-monetization -f scripts/e2e/22296/compose.yml -f scripts/e2e/22296/compose.monetization.yml)
"${COMPOSE[@]}" build backend frontend
"${COMPOSE[@]}" up -d postgres redis redpanda minio init-keys
"${COMPOSE[@]}" run --rm -T backend /app/.venv/bin/python /e2e/runtime.py migrate
"${COMPOSE[@]}" up -d --wait --force-recreate backend
"${COMPOSE[@]}" exec -T backend /app/.venv/bin/python /e2e/runtime.py check
"${COMPOSE[@]}" up -d --wait --force-recreate frontend nginx
docker build -f scripts/e2e/22296/Dockerfile.browser -t carcraft-documentregistry22296-browser:local .
bash scripts/e2e/22296/monetization-browser.sh
"${COMPOSE[@]}" logs --no-color --tail=80 backend frontend nginx
