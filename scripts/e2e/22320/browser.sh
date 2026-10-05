#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../../.."
docker run --rm --network host --ipc host \
  --mount "type=bind,source=$PWD/frontend,target=/source,readonly" \
  --mount type=bind,source=/tmp/carcraft-22320-e2e,target=/tmp/carcraft-22320-e2e \
  -e APPLICATION_SOURCES_E2E=1 \
  -e APPLICATION_SOURCES_FIXTURE=/tmp/carcraft-22320-e2e/manifest.json \
  -e PLAYWRIGHT_JUNIT_OUTPUT_NAME=/tmp/carcraft-22320-e2e/browser-results/junit.xml \
  -e PLAYWRIGHT_HTML_OUTPUT_DIR=/tmp/carcraft-22320-e2e/browser-report \
  --entrypoint sh carcraft-documentregistry22296-browser:local -c '
    cp -a /source/. /workspace/
    ln -s /app/node_modules /workspace/node_modules
    bun run test:e2e -- tests/e2e/applications/22320-source-type.spec.ts --project=desktop-chromium --workers=1 --output=/tmp/carcraft-22320-e2e/browser-results "$@"
  ' sh "$@"
