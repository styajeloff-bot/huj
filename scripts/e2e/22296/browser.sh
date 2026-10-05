#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../../.."
test -f /tmp/carcraft-22296-e2e-followup/manifest.json
# Reuse pinned application dependencies; all application requests use the isolated stack.
docker build -f scripts/e2e/22296/Dockerfile.browser -t carcraft-documentregistry22296-browser:local .
docker run --rm --network host --ipc host \
  --mount "type=bind,source=$PWD/frontend,target=/source,readonly" \
  --mount type=bind,source=/tmp/carcraft-22296-e2e-followup,target=/tmp/carcraft-22296-e2e-followup \
  -e DOCUMENT_REGISTRY_E2E=1 \
  -e DOCUMENT_REGISTRY_E2E_FIXTURE=/tmp/carcraft-22296-e2e-followup/manifest.json \
  -e PLAYWRIGHT_JUNIT_OUTPUT_NAME=/tmp/carcraft-22296-e2e-followup/browser-results/junit.xml \
  -e PLAYWRIGHT_HTML_OUTPUT_DIR=/tmp/carcraft-22296-e2e-followup/browser-report \
  --entrypoint sh carcraft-documentregistry22296-browser:local -c '
    # Legacy screenshot paths resolve into this new runtime, not the previous runtime.
    ln -s /tmp/carcraft-22296-e2e-followup /tmp/carcraft-22296-e2e
    cp -a /source/. /workspace/
    ln -s /app/node_modules /workspace/node_modules
    /app/node_modules/.bin/playwright test tests/e2e/document-registry tests/e2e/monetization/dropdown-position-22268.spec.ts --workers=1 --output=/tmp/carcraft-22296-e2e-followup/browser-results
  '
