#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE=(docker compose -p carcraft-22268-e2e -f "$SCRIPT_DIR/compose.yml")
"${COMPOSE[@]}" up -d postgres redis redpanda init-keys
"${COMPOSE[@]}" run --rm -T backend /app/.venv/bin/python /e2e/runtime.py migrate
"${COMPOSE[@]}" up -d --wait backend
"${COMPOSE[@]}" up -d --wait notification-runtime
"${COMPOSE[@]}" exec -T backend /app/.venv/bin/python /e2e/runtime.py seed
"${COMPOSE[@]}" exec -T backend /app/.venv/bin/python /e2e/runtime.py verify
"${COMPOSE[@]}" exec -T backend /app/.venv/bin/python /e2e/terms.py seed
"${COMPOSE[@]}" exec -T backend /app/.venv/bin/python /e2e/terms.py verify
"${COMPOSE[@]}" exec -T backend /app/.venv/bin/python /e2e/runtime.py check
"${COMPOSE[@]}" up -d frontend nginx
printf '%s\n' 'Isolated API checks complete. Browser manifest: /tmp/carcraft-22268-e2e/manifest.json'
