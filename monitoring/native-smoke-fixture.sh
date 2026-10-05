#!/bin/sh
set -eu

marker="${SMOKE_MARKER:-local_observability_smoke_native}"
service_name="${SMOKE_SERVICE_NAME:-postgres}"
native_format="${SMOKE_NATIVE_FORMAT:-known}"

case "$marker" in
  *[!A-Za-z0-9_.:-]*)
    echo "SMOKE_MARKER contains unsupported characters" >&2
    exit 2
    ;;
esac

case "$service_name" in
  postgres|redis|clickhouse|redpanda|redpanda-console|carcraft-api|carcraft-taskiq-worker|carcraft-frontend|carcraft-nginx) ;;
  *)
    echo "Unsupported native smoke service: ${service_name}" >&2
    exit 2
    ;;
esac

case "$native_format" in
  known|miss|sensitive) ;;
  *)
    echo "SMOKE_NATIVE_FORMAT must be known, miss, or sensitive" >&2
    exit 2
    ;;
esac

# Alloy's Docker source refreshes discovered targets asynchronously. Keep the
# fixture quiet through at least one complete source refresh so its sole event
# cannot be missed on a slower Docker Desktop host.
sleep 12

if [ "$native_format" = "miss" ]; then
  printf '%s\n' "parser_miss ${marker}"
  sleep 5
  exit 0
fi

if [ "$native_format" = "sensitive" ]; then
  printf '%s\n' "2026-09-04 00:00:00.000 UTC [1] LOG:  ${marker} person@example.test +375291112233 https://userinfo-secret@example.test/a?X-Amz-Credential=signed-secret&X-Amz-Security-Token=security-secret /s/magic-secret passport=passport-secret Authorization: Bearer authorization-secret"
  printf '%s\n' "2026-09-04 00:00:00.001 UTC ${marker} [1] DETAIL:  detail-secret"
  printf '%s\n' "2026-09-04 00:00:00.002 UTC ${marker} [1] STATEMENT:  statement-secret"
  sleep 5
  exit 0
fi

case "$service_name" in
  postgres)
    printf '%s\n' "2026-09-04 00:00:00.000 UTC [1] LOG:  ${marker}"
    ;;
  redis)
    printf '%s\n' "1:M 04 Sep 2026 00:00:00.000 * ${marker}"
    ;;
  clickhouse)
    printf '%s\n' "2026.09.04 00:00:00.000000 [ 1 ] <Information> ${marker}"
    ;;
  redpanda)
    printf '%s\n' "INFO  2026-09-04 00:00:00,000 ${marker}"
    ;;
  redpanda-console)
    printf '%s\n' "time=2026-09-04T00:00:00Z level=info msg=${marker}"
    ;;
  carcraft-api)
    printf '%s\n' "INFO  [alembic.runtime.migration] ${marker}"
    ;;
  carcraft-taskiq-worker)
    printf '%s\n' "Starting 2 worker processes. ${marker}"
    ;;
  carcraft-frontend)
    printf '%s\n' "✔ ${marker}"
    ;;
  carcraft-nginx)
    printf '%s\n' "/docker-entrypoint.sh: ${marker}"
    ;;
esac

sleep 5
