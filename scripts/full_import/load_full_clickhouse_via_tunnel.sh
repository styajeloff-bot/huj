#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${ENV_FILE:-${SCRIPT_DIR}/full_import.env}"
YES="false"

TABLES=(
  dwh_companies
  dwh_users
  dwh_vehicles
  dwh_leasing_company_applications
  dwh_application_vehicles
  dwh_exchange_requests
  dwh_exchange_bids
)

LK_MARTS=(
  dm_lk_daily_metrics
  dm_lk_application_funnel
  dm_lk_proposals
  dm_lk_financial_pipeline
)

usage() {
  cat <<'USAGE'
Usage:
  load_full_clickhouse_via_tunnel.sh [--env PATH] --yes

Loads generated ClickHouse JSONEachRow files through an already-open tunnel.
The script truncates the target DWH tables before inserting, then rebuilds
leasing-company analytics marts from the loaded DWH tables.

Required safety:
  FULL_IMPORT_ALLOW_DESTRUCTIVE=true in env file
  --yes command-line flag

CH_PASSWORD may be empty for local Docker ClickHouse. In that case the script
does not pass a password flag to clickhouse-client.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env)
      ENV_FILE="$2"
      shift 2
      ;;
    --yes)
      YES="true"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Required command not found: $1" >&2
    exit 1
  fi
}

resolve_clickhouse_client() {
  if [[ -n "${CLICKHOUSE_CLIENT_BIN:-}" ]]; then
    if [[ ! -x "$CLICKHOUSE_CLIENT_BIN" ]]; then
      echo "CLICKHOUSE_CLIENT_BIN is not executable: $CLICKHOUSE_CLIENT_BIN" >&2
      exit 1
    fi
    if [[ "$(basename "$CLICKHOUSE_CLIENT_BIN")" == "clickhouse-client" ]]; then
      CH_CLIENT=("$CLICKHOUSE_CLIENT_BIN")
    else
      CH_CLIENT=("$CLICKHOUSE_CLIENT_BIN" client)
    fi
    return
  fi

  if command -v clickhouse-client >/dev/null 2>&1; then
    CH_CLIENT=(clickhouse-client)
    return
  fi

  if command -v clickhouse >/dev/null 2>&1; then
    CH_CLIENT=(clickhouse client)
    return
  fi

  local repo_clickhouse="${SCRIPT_DIR}/../../backend/clickhouse"
  if [[ -x "$repo_clickhouse" ]]; then
    CH_CLIENT=("$repo_clickhouse" client)
    return
  fi

  cat >&2 <<'EOF'
Required ClickHouse client not found.

Install clickhouse-client, add clickhouse to PATH, or set:
  CLICKHOUSE_CLIENT_BIN="/absolute/path/to/clickhouse"

If installed with `curl https://clickhouse.com/ | sh` from backend/, use:
  CLICKHOUSE_CLIENT_BIN="/Users/a_belianskii/projects/carcraft-leadgenerator/backend/clickhouse"
EOF
  exit 1
}

require_var() {
  local name="$1"
  local value="${!name:-}"
  if [[ -z "$value" || "$value" == "CHANGE_ME" ]]; then
    echo "Required env value is missing or still CHANGE_ME: $name" >&2
    exit 1
  fi
}

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Env file not found: $ENV_FILE" >&2
  echo "Copy ${SCRIPT_DIR}/full_import.env.example to ${SCRIPT_DIR}/full_import.env first." >&2
  exit 1
fi

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

require_var FULL_IMPORT_TARGET_LABEL

if [[ "${FULL_IMPORT_ALLOW_DESTRUCTIVE:-false}" != "true" || "$YES" != "true" ]]; then
  cat >&2 <<EOF
Refusing destructive ClickHouse full import.

Set FULL_IMPORT_ALLOW_DESTRUCTIVE=true in:
  $ENV_FILE

Then run with:
  $0 --env "$ENV_FILE" --yes
EOF
  exit 1
fi

require_var FULL_IMPORT_BUNDLE_DIR
require_var CH_HOST
require_var CH_PORT
require_var CH_DATABASE
require_var CH_USER

resolve_clickhouse_client

CH_DATA_DIR="${CH_DATA_DIR:-}"
if [[ -z "$CH_DATA_DIR" ]]; then
  CH_DATA_DIR="${FULL_IMPORT_BUNDLE_DIR}/clickhouse/data"
fi

if [[ ! -d "$CH_DATA_DIR" ]]; then
  echo "ClickHouse data dir not found: $CH_DATA_DIR" >&2
  exit 1
fi

LK_MART_REBUILD_SQL="${LK_MART_REBUILD_SQL:-${SCRIPT_DIR}/lk_mart_rebuild.sql}"
if [[ ! -f "$LK_MART_REBUILD_SQL" ]]; then
  echo "LC mart rebuild SQL file not found: $LK_MART_REBUILD_SQL" >&2
  exit 1
fi

for table in "${TABLES[@]}"; do
  file="${CH_DATA_DIR}/${table}.jsonl"
  if [[ ! -f "$file" ]]; then
    echo "Missing ClickHouse JSONL file: $file" >&2
    exit 1
  fi
done

ch_args=(
  --host "$CH_HOST"
  --port "$CH_PORT"
  --user "$CH_USER"
  --database "$CH_DATABASE"
)

if [[ -n "${CH_PASSWORD:-}" ]]; then
  ch_args+=(--password "$CH_PASSWORD")
fi

if [[ "${CH_SECURE:-false}" == "true" ]]; then
  ch_args+=(--secure)
fi

max_partitions="${FULL_IMPORT_CH_MAX_PARTITIONS_PER_INSERT_BLOCK:-10000}"

echo "Target: ${FULL_IMPORT_TARGET_LABEL}"
echo "ClickHouse: ${CH_USER}@${CH_HOST}:${CH_PORT}/${CH_DATABASE}"
echo "Data: ${CH_DATA_DIR}"
echo "Client: ${CH_CLIENT[*]}"

echo "Checking ClickHouse connectivity and current counts..."
"${CH_CLIENT[@]}" "${ch_args[@]}" --query "SELECT 'database=' || currentDatabase()"
for table in "${TABLES[@]}"; do
  "${CH_CLIENT[@]}" "${ch_args[@]}" --query "SELECT '${table}_before=' || toString(count()) FROM ${table}"
done

echo "Running destructive ClickHouse DWH full import..."
for table in "${TABLES[@]}"; do
  file="${CH_DATA_DIR}/${table}.jsonl"
  echo "truncating ${table}"
  "${CH_CLIENT[@]}" "${ch_args[@]}" --query "TRUNCATE TABLE ${table}"
  echo "loading ${table} from ${file}"
  "${CH_CLIENT[@]}" "${ch_args[@]}" \
    --max_partitions_per_insert_block="$max_partitions" \
    --query "INSERT INTO ${table} FORMAT JSONEachRow" \
    < "$file"
done

echo "Rebuilding leasing-company analytics marts from loaded DWH tables..."
"${CH_CLIENT[@]}" "${ch_args[@]}" --multiquery < "$LK_MART_REBUILD_SQL"

echo "ClickHouse counts after import:"
for table in "${TABLES[@]}"; do
  "${CH_CLIENT[@]}" "${ch_args[@]}" --query "SELECT '${table}=' || toString(count()) FROM ${table}"
done
for table in "${LK_MARTS[@]}"; do
  "${CH_CLIENT[@]}" "${ch_args[@]}" --query "SELECT '${table}=' || toString(count()) FROM ${table}"
done
