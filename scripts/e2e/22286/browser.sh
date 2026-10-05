#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../../.."
runtime_dir=/tmp/carcraft-22286-e2e
[[ -f "$runtime_dir/manifest.json" ]] || { echo 'Run the 22286 API and UI fixtures first.' >&2; exit 2; }
case "${1:-}" in
  '') docker build -f scripts/e2e/22286/Dockerfile.browser -t carcraft-questionnaire22286-browser:local . ;;
  --skip-build) docker image inspect carcraft-questionnaire22286-browser:local >/dev/null ;;
  *) echo 'Usage: browser.sh [--skip-build]' >&2; exit 2 ;;
esac
docker compose -f scripts/e2e/22286/compose.yml exec -T backend /app/.venv/bin/python /e2e/ui_confidence_fixture.py
docker run --rm --network host --ipc host \
  -v "$PWD/frontend:/source:ro" -v "$runtime_dir:/runtime" \
  -e E2E_BASE_URL=http://localhost:18286 -e QUESTIONNAIRE_E2E_RUNTIME=/runtime \
  --entrypoint sh carcraft-questionnaire22286-browser:local -lc \
  'cp -a /source/. /workspace/; ln -s /app/node_modules /workspace/node_modules; cd /workspace; bun run test:e2e -- tests/e2e/questionnaire-22286.spec.ts tests/e2e/questionnaire-consent-document-22286.spec.ts tests/e2e/questionnaire-page-22286.spec.ts tests/e2e/questionnaire-bank-accounts-22286.spec.ts tests/e2e/questionnaire-management-company-22286.spec.ts tests/e2e/questionnaire-beneficiary-address-22286.spec.ts tests/e2e/questionnaire-passport-refresh-22286.spec.ts --workers=1 --reporter=line --output=/runtime/browser-results'
