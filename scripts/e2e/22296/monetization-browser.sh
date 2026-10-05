#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../../.."
COMPOSE=(docker compose -p carcraft-22296-monetization -f scripts/e2e/22296/compose.yml -f scripts/e2e/22296/compose.monetization.yml)
# Browser scenarios consume a bid and change manual terms. Give every run fresh
# sessions and fresh source/deal IDs instead of reusing a previous run's state.
"${COMPOSE[@]}" exec -T backend /app/.venv/bin/python /e2e/runtime.py seed
"${COMPOSE[@]}" exec -T backend /app/.venv/bin/python /e2e/monetization.py seed
"${COMPOSE[@]}" exec -T backend /app/.venv/bin/python /e2e/monetization.py verify
"${COMPOSE[@]}" exec -T backend /app/.venv/bin/python /e2e/financial_limits.py
docker run --rm --network host --ipc host \
  --mount "type=bind,source=$PWD/frontend,target=/source,readonly" \
  --mount type=bind,source=/tmp/carcraft-22296-monetization,target=/tmp/carcraft-22296-monetization \
  -e MONETIZATION_22296_E2E=1 \
  -e MONETIZATION_22296_FIXTURE=/tmp/carcraft-22296-monetization/monetization.manifest.json \
  -e PLAYWRIGHT_JUNIT_OUTPUT_NAME=/tmp/carcraft-22296-monetization/browser-results/junit.xml \
  -e PLAYWRIGHT_HTML_OUTPUT_DIR=/tmp/carcraft-22296-monetization/browser-report \
  --entrypoint sh carcraft-documentregistry22296-browser:local -c '
    cp -a /source/. /workspace/
    ln -s /app/node_modules /workspace/node_modules
    bun run test:e2e -- tests/e2e/monetization/monetization-22296.spec.ts --project=desktop-chromium --workers=1 --output=/tmp/carcraft-22296-monetization/browser-results "$@"
  ' sh "$@"
