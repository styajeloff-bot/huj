#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../../.."
COMPOSE=(docker compose -f scripts/e2e/22406/compose.yml)
skip_build=false
for argument in "$@"; do
  case "$argument" in
    --skip-build) skip_build=true ;;
    *) echo 'Usage: bash scripts/e2e/run.sh --suite 22406 [--skip-build]' >&2; exit 2 ;;
  esac
done
if [[ "$skip_build" == false ]]; then
  # Reuse the installed backend dependency image; application sources are copied afresh.
  docker image inspect carcraft-leadgenerator-local-backend:latest >/dev/null
  if ! docker image inspect carcraft-questionnaire22286-browser:local >/dev/null 2>&1; then
    docker build -t carcraft-questionnaire22286-browser:local -f scripts/e2e/22286/Dockerfile.browser .
  fi
  "${COMPOSE[@]}" build backend frontend
fi
collect_logs() {
  "${COMPOSE[@]}" logs --no-color 2>&1 | docker run --rm -i --user 0 \
    --entrypoint sh --mount type=bind,source=/tmp/carcraft-22406-e2e,target=/runtime \
    carcraft-22406-backend:local -c 'cat > /runtime/compose.log' || true
}
trap collect_logs EXIT
"${COMPOSE[@]}" up -d --wait postgres redis redpanda
"${COMPOSE[@]}" run --rm -T --no-deps init-keys
"${COMPOSE[@]}" run --rm -T --no-deps backend /app/.venv/bin/python /task/runtime.py migrate
"${COMPOSE[@]}" up -d --wait --force-recreate backend frontend nginx
"${COMPOSE[@]}" exec -T backend /app/.venv/bin/python /task/runtime.py seed
"${COMPOSE[@]}" exec -T backend /app/.venv/bin/python /task/modification.py seed
"${COMPOSE[@]}" exec -T backend /app/.venv/bin/python /task/deal_card.py seed
"${COMPOSE[@]}" exec -T backend /app/.venv/bin/python /task/modification.py verify
"${COMPOSE[@]}" exec -T backend /app/.venv/bin/python /task/deal_card.py verify
"${COMPOSE[@]}" exec -T backend /app/.venv/bin/python /task/trim_legacy.py verify-if-seeded
"${COMPOSE[@]}" exec -T backend /app/.venv/bin/python /task/runtime.py check
bash scripts/e2e/22406/browser.sh
printf '22406 E2E passed. Artifacts: /tmp/carcraft-22406-e2e\n'
