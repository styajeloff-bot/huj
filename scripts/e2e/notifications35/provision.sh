#!/usr/bin/env bash
# Explicit, non-destructive setup for the dedicated local E2E environment.
set -euo pipefail
[[ "${1:-}" == --execute ]] || { printf '%s\n' 'Usage: bash scripts/e2e/notifications35/provision.sh --execute'; exit 2; }
task_script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
task_repo_dir="$(cd -- "$task_script_dir/../../.." && pwd)"
task_state_dir=/tmp/carcraft-notifications35-followup-v2-runtime
[[ ! -L "$task_state_dir" ]] || { printf '%s\n' 'Refusing symlink state directory'; exit 1; }
if [[ ! -e "$task_state_dir" ]]; then mkdir -m 700 "$task_state_dir"; fi
[[ -d "$task_state_dir" && -O "$task_state_dir" ]] || { printf '%s\n' 'Unsafe runtime directory ownership'; exit 1; }
chmod 700 "$task_state_dir"
task_compose=(docker compose -p carcraft-notifications35-followup-v2 -f "$task_script_dir/compose.yml")
task_bootstrap=("${task_compose[@]}" -f "$task_script_dir/compose.bootstrap.yml")

for task_volume in runtime_keys postgres_data redis_data redpanda_data clickhouse_data; do
  task_volume_name="carcraft-notifications35-followup-v2_$task_volume"
  if docker volume inspect "$task_volume_name" >/dev/null 2>&1; then
    [[ "$(docker volume inspect --format '{{index .Labels "com.docker.compose.project"}}' "$task_volume_name")" == carcraft-notifications35-followup-v2 ]] || exit 1
  fi
done

cd -- "$task_repo_dir"
# A resumed setup may already have its own services up. Free only this isolated
# project's application/ClickHouse memory before building Nuxt; retain all data.
"${task_compose[@]}" stop event-worker taskiq-scheduler taskiq-worker backend frontend clickhouse
"${task_compose[@]}" build backend frontend
"${task_compose[@]}" up -d --wait postgres redis redpanda clickhouse
"${task_compose[@]}" up -d init-keys smtp
for task_initializer in init-keys; do
  task_initializer_id="$("${task_compose[@]}" ps --all -q "$task_initializer")"
  [[ -n "$task_initializer_id" && "$(docker wait "$task_initializer_id")" == 0 ]] || exit 1
done
schema() {
  local task_schema_service=event-worker
  if [[ "$1" == pg-* ]]; then task_schema_service=backend; fi
  "${task_compose[@]}" run --rm --no-deps -T -e PYTHONPATH=/app --entrypoint python "$task_schema_service" /e2e/provision.py "$1" --execute
}
schema pg-init
task_ch_state="$(schema ch-state)"
task_compat_active=false
cleanup() {
  if [[ "$task_compat_active" == true ]]; then
    "${task_compose[@]}" up -d --no-deps --force-recreate --wait clickhouse
  fi
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
if [[ "$task_ch_state" == empty ]]; then
  # Do not start consumers until the historical schema chain has finished.
  for task_service in event-worker taskiq-worker taskiq-scheduler; do
    [[ -z "$("${task_compose[@]}" ps --status running -q "$task_service")" ]] || { printf '%s\n' 'Workers already running against empty ClickHouse; refusing initialization'; exit 1; }
  done
  task_compat_active=true
  "${task_bootstrap[@]}" up -d --no-deps --force-recreate --wait clickhouse
  schema ch-init
  "${task_compose[@]}" up -d --no-deps --force-recreate --wait clickhouse
  task_compat_active=false
fi
schema verify
printf '%s\n' 'Isolated fixture schemas ready: PostgreSQL checkout head, ClickHouse 007. Run run.sh --execute.'
