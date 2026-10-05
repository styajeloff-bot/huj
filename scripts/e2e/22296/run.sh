#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../../.."
COMPOSE=(docker compose -f scripts/e2e/22296/compose.yml -f scripts/e2e/22296/compose.followup.yml)
"${COMPOSE[@]}" build backend frontend
"${COMPOSE[@]}" up -d postgres redis redpanda minio init-keys
# Never upgrade yesterday's conflicting revision 128 or overwrite its fixtures.
if [[ $("${COMPOSE[@]}" exec -T postgres psql -U documentregistry22296 -d postgres -Atqc "SELECT 1 FROM pg_database WHERE datname = 'documentregistry22296_followup'") != 1 ]]; then
  "${COMPOSE[@]}" exec -T postgres createdb -U documentregistry22296 -O documentregistry22296 documentregistry22296_followup
fi
# Continue the existing consumer group's offsets only after the new schema is ready.
"${COMPOSE[@]}" stop notification-runtime
"${COMPOSE[@]}" run --rm -T backend /app/.venv/bin/python /e2e/runtime.py migrate
"${COMPOSE[@]}" up -d --wait backend
"${COMPOSE[@]}" exec -T backend /app/.venv/bin/python /e2e/runtime.py seed
"${COMPOSE[@]}" up -d --wait notification-runtime
"${COMPOSE[@]}" exec -T backend /app/.venv/bin/python /e2e/runtime.py verify
"${COMPOSE[@]}" exec -T backend /app/.venv/bin/python /e2e/acceptance.py
"${COMPOSE[@]}" exec -T backend /app/.venv/bin/python /e2e/transactions.py
bash scripts/e2e/22296/cleanup_locks.sh
python3 scripts/e2e/22296/taskiq_run.py
"${COMPOSE[@]}" exec -T backend /app/.venv/bin/python /e2e/runtime.py check
# The isolated S3 outage must always be recovered, including on failed assertions.
trap '"${COMPOSE[@]}" up -d --wait minio' EXIT
"${COMPOSE[@]}" stop minio
"${COMPOSE[@]}" exec -T backend /app/.venv/bin/python /e2e/faults.py unavailable
"${COMPOSE[@]}" up -d --wait minio
trap - EXIT
"${COMPOSE[@]}" exec -T backend /app/.venv/bin/python /e2e/faults.py recovered
"${COMPOSE[@]}" up -d --wait --force-recreate frontend nginx
"${COMPOSE[@]}" exec -T backend /app/.venv/bin/python -c 'import sys,asyncio;sys.path.insert(0,"/e2e");from registry import verify_proxy_upload;asyncio.run(verify_proxy_upload())'
bash scripts/e2e/22296/browser.sh
