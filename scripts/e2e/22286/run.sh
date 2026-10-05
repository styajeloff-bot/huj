#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../../.."
COMPOSE=(docker compose -f scripts/e2e/22286/compose.yml)
runtime_dir=/tmp/carcraft-22286-e2e
skip_build=false
api_only=false
for argument in "$@"; do
  case "$argument" in
    --skip-build) skip_build=true ;;
    --api-only) api_only=true ;;
    *) echo "Usage: bash scripts/e2e/run.sh --suite 22286 [--skip-build] [--api-only]" >&2; exit 2 ;;
  esac
done
command -v docker >/dev/null
mkdir -p "$runtime_dir"
if [[ "$skip_build" == false ]]; then
  sdk_ssh="${E2E_SDK_SSH_KEY:-${SDK_SSH_KEY:-${SSH_AUTH_SOCK:-}}}"
  if [[ -z "$sdk_ssh" ]]; then
    echo "Set E2E_SDK_SSH_KEY (private SDK deploy-key path) or start an SSH agent with access to carcraft-bor." >&2
    echo "The locked SDK is installed through a BuildKit SSH mount; no stub is used." >&2
    exit 2
  fi
  "${COMPOSE[@]}" build --ssh "default=$sdk_ssh" backend
  if [[ "$api_only" == false ]]; then
    "${COMPOSE[@]}" build frontend
  fi
fi
collect_logs() {
  "${COMPOSE[@]}" logs --no-color 2>&1 | docker run --rm -i --user 0 \
    --entrypoint /bin/sh -v "$runtime_dir:/runtime" \
    carcraft-questionnaire22286-backend:local -c 'cat > /runtime/compose.log' || true
}
trap collect_logs EXIT
"${COMPOSE[@]}" up -d --wait postgres redis redpanda minio
"${COMPOSE[@]}" run --rm -T --no-deps init-keys
"${COMPOSE[@]}" run --rm -T --no-deps backend /app/.venv/bin/python /e2e/acceptance.py migrate
"${COMPOSE[@]}" run --rm -T --no-deps backend /app/.venv/bin/python /e2e/migration_acceptance.py
"${COMPOSE[@]}" run --rm -T --no-deps backend /app/.venv/bin/python /e2e/management_migration_acceptance.py
"${COMPOSE[@]}" up -d --wait --force-recreate backend provider-fixture
"${COMPOSE[@]}" exec -T backend /app/.venv/bin/python /e2e/acceptance.py seed
"${COMPOSE[@]}" exec -T backend /app/.venv/bin/python /e2e/acceptance.py roles
# Provider mode is shared within this isolated stack; these suites are sequential.
"${COMPOSE[@]}" exec -T backend /app/.venv/bin/python /e2e/acceptance.py verify
"${COMPOSE[@]}" exec -T backend /app/.venv/bin/python /e2e/core_acceptance.py
"${COMPOSE[@]}" exec -T backend /app/.venv/bin/python /e2e/concurrency_acceptance.py
"${COMPOSE[@]}" exec -T backend /app/.venv/bin/python /e2e/source_acceptance.py
"${COMPOSE[@]}" exec -T backend /app/.venv/bin/python /e2e/foreign_name_acceptance.py
"${COMPOSE[@]}" exec -T backend /app/.venv/bin/python /e2e/management_company_acceptance.py
"${COMPOSE[@]}" exec -T backend /app/.venv/bin/python /e2e/bank_accounts_acceptance.py
"${COMPOSE[@]}" exec -T backend /app/.venv/bin/python /e2e/bank_acceptance.py
"${COMPOSE[@]}" exec -T backend /app/.venv/bin/python /e2e/purpose_acceptance.py
"${COMPOSE[@]}" exec -T backend /app/.venv/bin/python /e2e/readiness_acceptance.py
"${COMPOSE[@]}" exec -T backend /app/.venv/bin/python /e2e/defaults_acceptance.py
"${COMPOSE[@]}" exec -T backend /app/.venv/bin/python /e2e/address_acceptance.py
"${COMPOSE[@]}" exec -T backend /app/.venv/bin/python /e2e/unavailable_fields_acceptance.py
"${COMPOSE[@]}" exec -T backend /app/.venv/bin/python /e2e/consent_document_acceptance.py
"${COMPOSE[@]}" exec -T backend /app/.venv/bin/python /e2e/acceptance.py check
if [[ "$api_only" == false ]]; then
  "${COMPOSE[@]}" exec -T backend /app/.venv/bin/python /e2e/acceptance.py ui-seed
  "${COMPOSE[@]}" exec -T backend /app/.venv/bin/python /e2e/beneficiary_address_acceptance.py
  "${COMPOSE[@]}" exec -T backend /app/.venv/bin/python /e2e/passport_refresh_acceptance.py
  "${COMPOSE[@]}" up -d --wait --force-recreate frontend nginx
  if [[ "$skip_build" == true ]]; then
    bash scripts/e2e/22286/browser.sh --skip-build
  else
    bash scripts/e2e/22286/browser.sh
  fi
fi
printf '22286 E2E passed (api_only=%s, cached_images=%s). Artifacts: %s\n' "$api_only" "$skip_build" "$runtime_dir"
