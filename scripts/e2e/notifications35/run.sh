#!/usr/bin/env bash
# Repeat the approved local acceptance on the dedicated, already-provisioned
# notifications35 runtime (PostgreSQL checkout head / ClickHouse head 007).
# It never resets volumes, prunes Docker, changes another project, or sends mail
# outside Mailpit. Use provision.sh --execute for first-time isolated setup.
set -euo pipefail

if [[ "${1:-}" != --execute ]]; then
  printf '%s\n' 'Usage: bash scripts/e2e/notifications35/run.sh --execute'
  printf '%s\n' 'First run: bash scripts/e2e/notifications35/provision.sh --execute'
  printf '%s\n' 'Requires Docker, installed frontend dependencies, Bun, ripgrep, and Playwright Chromium.'
  exit 2
fi

task_script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
task_repo_dir="$(cd -- "$task_script_dir/../../.." && pwd)"
task_state_dir=/tmp/carcraft-notifications35-followup-v2-runtime
task_compose_file="$task_script_dir/compose.yml"
task_compose=(docker compose -p carcraft-notifications35-followup-v2 -f "$task_compose_file")
for task_tool in docker bun rg; do
  command -v "$task_tool" >/dev/null || { printf 'Missing required tool: %s\n' "$task_tool"; exit 1; }
done
[[ -d "$task_state_dir" && ! -L "$task_state_dir" && -O "$task_state_dir" ]] || { printf '%s\n' 'Missing or unsafe isolated runtime directory'; exit 1; }
chmod 700 "$task_state_dir"

# Refuse implicit fresh volumes or another application DB.
task_pg_container="$("${task_compose[@]}" ps -q postgres)"
[[ -n "$task_pg_container" ]] || { printf '%s\n' 'Start/provision the isolated runtime first'; exit 1; }
[[ "$(docker inspect --format '{{index .Config.Labels "com.docker.compose.project"}}/{{index .Config.Labels "com.docker.compose.service"}}' "$task_pg_container")" == carcraft-notifications35-followup-v2/postgres ]]
[[ "$("${task_compose[@]}" exec -T clickhouse clickhouse-client --query 'SELECT version_num FROM default.alembic_version')" == 007 ]]

task_run_id="$(date -u +%Y%m%dT%H%M%SZ)"
task_started_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
task_report_dir="$task_state_dir/run-$task_run_id"
mkdir -m 700 "$task_report_dir"
task_smtp_container="$("${task_compose[@]}" ps -q smtp)"
cleanup() {
  # Fault injection must be undone even if the test runner is interrupted.
  if [[ -n "$task_smtp_container" && "$(docker inspect --format '{{.State.Paused}}' "$task_smtp_container" 2>/dev/null || true)" == true ]]; then
    docker unpause "$task_smtp_container" >/dev/null
  fi
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

cd -- "$task_repo_dir"
# This project is exclusively owned by the synthetic acceptance harness. Release
# its application/ClickHouse memory while Nuxt builds; do not stop other projects
# or remove any container data/volumes. Restore ClickHouse before schema verify.
"${task_compose[@]}" stop event-worker taskiq-scheduler taskiq-worker backend frontend clickhouse >"$task_report_dir/stop-for-build.log" 2>&1
"${task_compose[@]}" build backend frontend >"$task_report_dir/build.log" 2>&1
"${task_compose[@]}" up -d --wait clickhouse >"$task_report_dir/storage-start.log" 2>&1
"${task_compose[@]}" run --rm --no-deps -T -e PYTHONPATH=/app --entrypoint python backend /e2e/provision.py verify --execute
"${task_compose[@]}" up -d --force-recreate backend frontend nginx event-worker taskiq-worker taskiq-scheduler >"$task_report_dir/start.log" 2>&1
runtime() {
  "${task_compose[@]}" exec -T -e PYTHONPATH=/app backend python /e2e/runtime.py "$@" --execute
}
runtime prepare >"$task_report_dir/scenario.log"
runtime regressions >"$task_report_dir/http.log" 2>&1
runtime smoke >"$task_report_dir/flow.log" 2>&1
runtime dwh >"$task_report_dir/dwh.log" 2>&1
runtime dlq >"$task_report_dir/dlq.log" 2>&1
"${task_compose[@]}" exec -T -e PYTHONPATH=/app backend python /e2e/followup.py prepare --execute >"$task_report_dir/followup-fixture.log" 2>&1
"${task_compose[@]}" exec -T -e PYTHONPATH=/app backend python /e2e/followup.py context-prepare --execute >"$task_report_dir/context-fixture.log" 2>&1
"${task_compose[@]}" exec -T -e PYTHONPATH=/app backend python /e2e/followup.py grouping --execute >"$task_report_dir/followup-grouping.log" 2>&1
cd -- "$task_repo_dir/frontend"
NOTIFICATIONS35_E2E=1 NOTIFICATIONS35_COMPOSE="$task_compose_file" \
  PLAYWRIGHT_JUNIT_OUTPUT_NAME="$task_report_dir/browser-junit.xml" \
  bunx playwright test tests/e2e/notifications/35-local-runtime.spec.ts \
    --workers=1 --output="$task_report_dir/browser" >"$task_report_dir/browser.log" 2>&1
NOTIFICATIONS35_E2E=1 NOTIFICATIONS35_COMPOSE="$task_compose_file" \
  PLAYWRIGHT_JUNIT_OUTPUT_NAME="$task_report_dir/followup-browser-junit.xml" \
  bunx playwright test tests/e2e/notifications/35-followup.spec.ts tests/e2e/notifications/35-take-work.spec.ts tests/e2e/notifications/35-followup-context.spec.ts \
    --workers=1 --output="$task_report_dir/followup-browser" >"$task_report_dir/followup-browser.log" 2>&1
"${task_compose[@]}" logs --no-color --since "$task_started_at" backend event-worker taskiq-worker taskiq-scheduler frontend >"$task_report_dir/runtime.log" 2>&1
if rg -q '"level":"error"|clickhouse_batch_insert_failed|Error serializing' "$task_report_dir/runtime.log"; then
  printf 'Runtime errors detected; inspect %s/runtime.log\n' "$task_report_dir"
  exit 1
else
  task_log_check_exit=$?
  [[ "$task_log_check_exit" == 1 ]] || { printf '%s\n' 'Runtime log validation failed'; exit "$task_log_check_exit"; }
fi
printf 'Local E2E passed. Reports: %s\n' "$task_report_dir"
