#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../../.."
test -f /tmp/carcraft-22406-e2e/manifest.json
if (($# == 0)); then
  set -- 'tests/e2e/monetization/.*22406.spec.ts'
fi
docker run --rm --network host --ipc host \
  --mount "type=bind,source=$PWD/frontend,target=/source,readonly" \
  --mount type=bind,source=/tmp/carcraft-22406-e2e,target=/tmp/carcraft-22406-e2e \
  -e MONETIZATION_E2E=1 \
  -e MONETIZATION_E2E_FIXTURE=/tmp/carcraft-22406-e2e/manifest.json \
  -e MONETIZATION_DEAL_CARD_E2E=1 \
  -e MONETIZATION_22406_E2E=1 \
  -e PLAYWRIGHT_JUNIT_OUTPUT_NAME=/tmp/carcraft-22406-e2e/browser-results/junit.xml \
  -e PLAYWRIGHT_HTML_OUTPUT_DIR=/tmp/carcraft-22406-e2e/browser-report \
  --entrypoint sh carcraft-questionnaire22286-browser:local -c '
    cp -a /source/. /workspace/
    ln -s /app/node_modules /workspace/node_modules
    /app/node_modules/.bin/playwright test "$@" --workers=1 --output=/tmp/carcraft-22406-e2e/browser-results
  ' sh "$@"
