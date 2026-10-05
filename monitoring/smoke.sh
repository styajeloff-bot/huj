#!/bin/sh
set -eu

project_root="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
base_compose="${project_root}/docker-compose.yml"
observability_compose="${project_root}/compose.observability.yml"
grafana_port="${GRAFANA_PORT:-3001}"
grafana_url="http://127.0.0.1:${grafana_port}"

for command_name in docker curl jq uuidgen; do
  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "Required command is missing: ${command_name}" >&2
    exit 2
  fi
done

case "$grafana_port" in
  ''|*[!0-9]*)
    echo "GRAFANA_PORT must be a local numeric TCP port" >&2
    exit 2
    ;;
esac

if [ ! -f "$base_compose" ]; then
  echo "Local base compose is missing: ${base_compose}" >&2
  exit 2
fi

compose_observability() {
  docker compose \
    -f "$base_compose" \
    -f "$observability_compose" \
    --profile observability \
    "$@"
}

wait_for_url() {
  url="$1"
  name="$2"
  attempts=0
  until curl -fsS "$url" >/dev/null 2>&1; do
    attempts=$((attempts + 1))
    if [ "$attempts" -ge 60 ]; then
      echo "Timed out waiting for ${name}: ${url}" >&2
      return 1
    fi
    sleep 2
  done
}

loki_query_range() {
  query="$1"
  now_seconds="$(date +%s)"
  start_seconds=$((now_seconds - 600))
  curl -fsS -G \
    "${grafana_url}/api/datasources/proxy/uid/loki/loki/api/v1/query_range" \
    --data-urlencode "query=${query}" \
    --data-urlencode "start=${start_seconds}000000000" \
    --data-urlencode "end=${now_seconds}000000000" \
    --data-urlencode "limit=1000"
}

wait_for_query() {
  query="$1"
  attempts=0
  while [ "$attempts" -lt 30 ]; do
    response="$(loki_query_range "$query")"
    if printf '%s' "$response" | jq -e '.status == "success" and (.data.result | length > 0)' >/dev/null; then
      printf '%s' "$response"
      return 0
    fi
    attempts=$((attempts + 1))
    sleep 2
  done
  echo "Timed out waiting for Loki query: ${query}" >&2
  return 1
}

fixture_containers=""
cleanup_fixture_containers() {
  for fixture_container in $fixture_containers; do
    docker rm -f "$fixture_container" >/dev/null 2>&1 || true
  done
}
trap cleanup_fixture_containers EXIT INT TERM

echo "Starting the application with the local observability profile..."
compose_observability up -d --build
# Nginx resolves compose upstream names when it starts. If backend was rebuilt
# and recreated while Nginx was already running, restart only the proxy so it
# picks up the new container address before the HTTP smoke request.
compose_observability up -d --force-recreate nginx

wait_for_url "${grafana_url}/api/health" "Grafana"
wait_for_url "http://127.0.0.1/api/v1/health" "CarCraft API"

request_id="$(uuidgen | tr '[:upper:]' '[:lower:]')"
http_smoke_path="/api/v1/observability-smoke/${request_id}"
http_query_secret="query-secret-${request_id}"
http_status="$(curl -sS -o /dev/null -w '%{http_code}' \
  -H "X-Request-ID: ${request_id}" \
  "http://127.0.0.1${http_smoke_path}?token=${http_query_secret}")"
if [ "$http_status" -ne 404 ]; then
  echo "Expected HTTP path smoke request to return 404, got ${http_status}" >&2
  exit 1
fi

marker="local_observability_smoke_$(date -u +%Y%m%dT%H%M%SZ)_$$"
echo "Writing sanitized fixture events with marker ${marker}..."
json_fixture_container="carcraft-observability-json-${marker}"
fixture_containers="${fixture_containers} ${json_fixture_container}"
SMOKE_MARKER="$marker" docker compose \
  -f "$base_compose" \
  -f "$observability_compose" \
  --profile observability \
  --profile observability-smoke \
  run --name "$json_fixture_container" observability-smoke

smoke_query="{namespace=\"carcraft-leadgenerator\",environment=\"local\",service_name=\"carcraft-api\"} |= \"${marker}\""
smoke_response="$(wait_for_query "$smoke_query")"
smoke_lines="$(printf '%s' "$smoke_response" | jq -r '.data.result[].values[][1]')"

printf '%s\n' "$smoke_lines" | jq -e -s '
  length == 5 and
  all(.[];
    (.timestamp | type == "string") and
    .schema_version == 1 and
    (.level | type == "string") and
    .service_name == "carcraft-api" and
    (.component | type == "string") and
    (.event | type == "string") and
    (.message | type == "string") and
    .environment == "local" and
    (.service_version | type == "string")
  ) and
  ([.[].level] | sort | unique) == ["critical", "debug", "error", "info", "warning"]
' >/dev/null

if printf '%s\n' "$smoke_lines" | grep -Eiq \
  'authorization|set-cookie|access_token|refresh_token|api_key|secret_key|password|signature'; then
  echo "Sensitive-key marker found in smoke log output" >&2
  exit 1
fi

# Exercise every known native parser with controlled, read-only fixture output.
# This validates parser coverage without assuming a real database or broker has
# happened to emit a line during the short smoke window.
for native_service in \
  postgres redis clickhouse redpanda redpanda-console carcraft-api \
  carcraft-taskiq-worker carcraft-frontend carcraft-nginx; do
  native_marker="${marker}_native_${native_service}"
  native_fixture_container="carcraft-observability-native-${native_service}-${marker}"
  fixture_containers="${fixture_containers} ${native_fixture_container}"
  SMOKE_MARKER="$native_marker" \
  SMOKE_NATIVE_FORMAT=known \
  SMOKE_SERVICE_NAME="$native_service" \
    docker compose \
      -f "$base_compose" \
      -f "$observability_compose" \
      --profile observability \
      --profile observability-smoke \
      run --name "$native_fixture_container" observability-native-smoke >/dev/null

  native_query="{namespace=\"carcraft-leadgenerator\",service_name=\"${native_service}\",level=\"info\"} |= \"${native_marker}\" | json | line_format \"{{.message}}\""
  native_response="$(wait_for_query "$native_query")"
  native_count="$(printf '%s' "$native_response" | jq '[.data.result[].values[]] | length')"
  if [ "$native_count" -ne 1 ]; then
    echo "Expected one parsed native event for ${native_service}, got ${native_count}" >&2
    exit 1
  fi
  if ! printf '%s' "$native_response" | jq -e --arg marker "$native_marker" '
    [.data.result[].values[][1]] | length == 1 and all(.[]; contains($marker))
  ' >/dev/null; then
    echo "Native message metadata is missing for ${native_service}" >&2
    exit 1
  fi
done

sensitive_marker="${marker}_collector_redaction"
sensitive_container="carcraft-observability-sensitive-${marker}"
fixture_containers="${fixture_containers} ${sensitive_container}"
SMOKE_MARKER="$sensitive_marker" \
SMOKE_NATIVE_FORMAT=sensitive \
SMOKE_SERVICE_NAME=postgres \
  docker compose \
    -f "$base_compose" \
    -f "$observability_compose" \
    --profile observability \
    --profile observability-smoke \
    run --name "$sensitive_container" observability-native-smoke >/dev/null

sensitive_query="{namespace=\"carcraft-leadgenerator\",service_name=\"postgres\"} |= \"${sensitive_marker}\""
sensitive_response="$(wait_for_query "$sensitive_query")"
sensitive_lines="$(printf '%s' "$sensitive_response" | jq -r '.data.result[].values[][1]')"
sensitive_count="$(printf '%s' "$sensitive_response" | jq '[.data.result[].values[]] | length')"
if [ "$sensitive_count" -ne 3 ]; then
  echo "Expected three collector-redaction events, got ${sensitive_count}" >&2
  exit 1
fi
if printf '%s\n' "$sensitive_lines" | grep -Eq \
  'person@example[.]test|[+]375291112233|userinfo-secret|signed-secret|security-secret|magic-secret|passport-secret|authorization-secret|detail-secret|statement-secret'; then
  echo "Collector redaction leaked a controlled sensitive value" >&2
  exit 1
fi
if ! printf '%s\n' "$sensitive_lines" | grep -Fq '[REDACTED]'; then
  echo "Collector redaction marker is missing" >&2
  exit 1
fi

parser_miss_marker="${marker}_controlled_parser_miss"
parser_miss_container="carcraft-observability-parser-miss-${marker}"
fixture_containers="${fixture_containers} ${parser_miss_container}"
SMOKE_MARKER="$parser_miss_marker" \
SMOKE_NATIVE_FORMAT=miss \
SMOKE_SERVICE_NAME=postgres \
  docker compose \
    -f "$base_compose" \
    -f "$observability_compose" \
    --profile observability \
    --profile observability-smoke \
    run --name "$parser_miss_container" observability-native-smoke >/dev/null

parser_miss_query="{namespace=\"carcraft-leadgenerator\",service_name=\"postgres\",level=\"unknown\"} |= \"${parser_miss_marker}\""
parser_miss_response="$(wait_for_query "$parser_miss_query")"
parser_miss_count="$(printf '%s' "$parser_miss_response" | jq '[.data.result[].values[]] | length')"
if [ "$parser_miss_count" -ne 1 ]; then
  echo "Expected one controlled parser miss, got ${parser_miss_count}" >&2
  exit 1
fi

task_correlation_id="$(uuidgen | tr '[:upper:]' '[:lower:]')"
task_marker="${marker}_task"
compose_observability exec -T taskiq-worker python -c \
  "import asyncio; from application.tasks.observability import enqueue_observability_smoke; asyncio.run(enqueue_observability_smoke(marker='${task_marker}', correlation_id='${task_correlation_id}'))"

task_query="{namespace=\"carcraft-leadgenerator\",service_name=\"carcraft-taskiq-worker\"} | json | event=\"task.completed\" | task_name=\"observability.smoke\" | correlation_id=\"${task_correlation_id}\""
task_response="$(wait_for_query "$task_query")"
task_count="$(printf '%s' "$task_response" | jq '[.data.result[].values[]] | length')"
if [ "$task_count" -ne 1 ]; then
  echo "Expected exactly one Taskiq terminal event for ${task_correlation_id}, got ${task_count}" >&2
  exit 1
fi

http_query="{namespace=\"carcraft-leadgenerator\",service_name=\"carcraft-api\"} | json | request_id=\"${request_id}\" | event=~\"http[.]request[.](completed|failed)\""
http_response="$(wait_for_query "$http_query")"
http_count="$(printf '%s' "$http_response" | jq '[.data.result[].values[]] | length')"
if [ "$http_count" -ne 1 ]; then
  echo "Expected exactly one backend HTTP summary for ${request_id}, got ${http_count}" >&2
  exit 1
fi
if ! printf '%s' "$http_response" | jq -e --arg expected_path "$http_smoke_path" '
  [.data.result[].values[][1] | fromjson] |
  length == 1 and
  .[0].http_route == $expected_path and
  (.[0].message | contains($expected_path))
' >/dev/null; then
  echo "Backend HTTP summary does not contain the full requested path" >&2
  exit 1
fi
if printf '%s' "$http_response" | grep -Fq "$http_query_secret"; then
  echo "Backend HTTP summary leaked the query string" >&2
  exit 1
fi

echo "Smoke checks passed: JSON levels, native messages/parsers, collector redaction, parser miss, HTTP, and Taskiq correlation."
echo "Open ${grafana_url}/d/carcraft-structured-logs/carcraft-structured-logs"
