#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
FASTAPI_DIR="${ROOT_DIR}/fastapi"
ENV_FILE="${ENV_FILE:-${SCRIPT_DIR}/full_import.env}"
YES="false"
SCHEMA_RESET_ALLOW_OVERRIDE="${FULL_IMPORT_ALLOW_SCHEMA_RESET:-}"

usage() {
  cat <<'USAGE'
Usage:
  reset_postgres_schema_via_tunnel.sh [--env PATH] --yes

Drops and recreates the target Postgres public schema through an already-open
tunnel, then rebuilds it with Alembic head from the current FastAPI code.

Required safety:
  FULL_IMPORT_ALLOW_SCHEMA_RESET=true in env file or process environment
  --yes command-line flag
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

if [[ -n "$SCHEMA_RESET_ALLOW_OVERRIDE" ]]; then
  FULL_IMPORT_ALLOW_SCHEMA_RESET="$SCHEMA_RESET_ALLOW_OVERRIDE"
fi

require_var FULL_IMPORT_TARGET_LABEL

if [[ "${FULL_IMPORT_ALLOW_SCHEMA_RESET:-false}" != "true" || "$YES" != "true" ]]; then
  cat >&2 <<EOF
Refusing destructive Postgres schema reset.

This command drops and recreates the public schema on:
  ${PGUSER:-CHANGE_ME}@${PGHOST:-CHANGE_ME}:${PGPORT:-CHANGE_ME}/${PGDATABASE:-CHANGE_ME}

Set FULL_IMPORT_ALLOW_SCHEMA_RESET=true in:
  $ENV_FILE

Then run with:
  $0 --env "$ENV_FILE" --yes
EOF
  exit 1
fi

require_command psql
require_command uv
require_var PGHOST
require_var PGPORT
require_var PGDATABASE
require_var PGUSER
require_var PGPASSWORD

psql_cmd=(
  psql
  -h "$PGHOST"
  -p "$PGPORT"
  -U "$PGUSER"
  -d "$PGDATABASE"
  -v ON_ERROR_STOP=1
)

echo "Target: ${FULL_IMPORT_TARGET_LABEL}"
echo "Postgres: ${PGUSER}@${PGHOST}:${PGPORT}/${PGDATABASE}"
echo "Dropping and recreating public schema..."

PGPASSWORD="$PGPASSWORD" "${psql_cmd[@]}" <<'SQL'
DROP SCHEMA IF EXISTS public CASCADE;
CREATE SCHEMA public;
GRANT ALL ON SCHEMA public TO public;
CREATE EXTENSION IF NOT EXISTS pgcrypto;
SQL

echo "Running Alembic migrations to head..."
(
  cd "$FASTAPI_DIR"
  DB_HOST="$PGHOST" \
  DB_PORT="$PGPORT" \
  DB_NAME="$PGDATABASE" \
  DB_USER="$PGUSER" \
  DB_PASSWORD="$PGPASSWORD" \
    uv run alembic upgrade head
)

echo "Verifying rebuilt UUID schema..."
"${SCRIPT_DIR}/load_full_postgres_via_tunnel.sh" --env "$ENV_FILE" --preflight-only
