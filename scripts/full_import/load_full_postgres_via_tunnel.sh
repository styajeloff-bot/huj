#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${ENV_FILE:-${SCRIPT_DIR}/full_import.env}"
YES="false"
PREFLIGHT_ONLY="false"

usage() {
  cat <<'USAGE'
Usage:
  load_full_postgres_via_tunnel.sh [--env PATH] --yes
  load_full_postgres_via_tunnel.sh [--env PATH] --preflight-only

Loads the generated full import Postgres bundle through an already-open tunnel.
The generated load.sql is destructive for the imported business layer.

The schema preflight is non-destructive and checks that the target database was
rebuilt with the current UUID-based Alembic schema before loading UUID data.

Required safety:
  FULL_IMPORT_ALLOW_DESTRUCTIVE=true in env file
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
    --preflight-only)
      PREFLIGHT_ONLY="true"
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

schema_preflight_sql() {
  cat <<'SQL'
WITH expected(table_name, column_name, expected_udt_name) AS (
  VALUES
    ('cities', 'id', 'uuid'),
    ('companies', 'id', 'uuid'),
    ('users', 'id', 'uuid'),
    ('users', 'company_id', 'uuid'),
    ('vehicles', 'id', 'uuid'),
    ('vehicles', 'dealer_id', 'uuid'),
    ('warehouses', 'id', 'uuid'),
    ('warehouses', 'city_id', 'uuid'),
    ('warehouses', 'dealer_id', 'uuid'),
    ('warehouses', 'company_id', 'uuid'),
    ('leasing_companies', 'id', 'uuid'),
    ('leasing_companies', 'company_id', 'uuid'),
    ('vehicle_warehouses', 'id', 'uuid'),
    ('vehicle_warehouses', 'vehicle_id', 'uuid'),
    ('vehicle_warehouses', 'warehouse_id', 'uuid'),
    ('leasing_applications', 'id', 'uuid'),
    ('leasing_applications', 'company_id', 'uuid'),
    ('leasing_applications', 'vehicle_id', 'uuid'),
    ('leasing_applications', 'dealer_company_id', 'uuid'),
    ('leasing_applications', 'selected_leasing_companies', '_uuid'),
    ('leasing_company_applications', 'id', 'uuid'),
    ('leasing_company_applications', 'leasing_company_id', 'uuid'),
    ('leasing_company_applications', 'application_id', 'uuid'),
    ('application_vehicles', 'id', 'uuid'),
    ('application_vehicles', 'application_id', 'uuid'),
    ('application_vehicles', 'vehicle_id', 'uuid'),
    ('exchange_requests', 'id', 'uuid'),
    ('exchange_requests', 'lc_user_id', 'uuid'),
    ('exchange_requests', 'vehicle_id', 'uuid'),
    ('exchange_requests', 'distributor_id', 'uuid'),
    ('exchange_requests', 'accepted_bid_id', 'uuid'),
    ('exchange_bids', 'id', 'uuid'),
    ('exchange_bids', 'request_id', 'uuid'),
    ('exchange_bids', 'dealer_id', 'uuid'),
    ('exchange_bids', 'distributor_id', 'uuid'),
    ('distributor_dealer_links', 'distributor_company_id', 'uuid'),
    ('distributor_dealer_links', 'dealer_company_id', 'uuid')
),
actual AS (
  SELECT
    table_name,
    column_name,
    udt_name,
    column_default
  FROM information_schema.columns
  WHERE table_schema = current_schema()
)
SELECT
  expected.table_name || '.' || expected.column_name AS checked_column,
  COALESCE(actual.udt_name, '<missing>') AS actual_udt_name,
  expected.expected_udt_name,
  COALESCE(actual.column_default, '') AS column_default,
  CASE
    WHEN actual.udt_name IS NULL THEN 'missing column'
    WHEN actual.udt_name <> expected.expected_udt_name THEN
      'expected ' || expected.expected_udt_name || ' but found ' || actual.udt_name
    WHEN COALESCE(actual.column_default, '') LIKE 'nextval(%' THEN
      'serial nextval default is not allowed for imported UUID schema'
  END AS issue
FROM expected
LEFT JOIN actual
  ON actual.table_name = expected.table_name
 AND actual.column_name = expected.column_name
WHERE actual.udt_name IS NULL
   OR actual.udt_name <> expected.expected_udt_name
   OR COALESCE(actual.column_default, '') LIKE 'nextval(%'
ORDER BY checked_column;
SQL
}

run_schema_preflight() {
  echo "Checking Postgres UUID schema preflight..."

  local failures
  failures="$(PGPASSWORD="$PGPASSWORD" "${psql_cmd[@]}" -P pager=off -F $'\t' -Atc "$(schema_preflight_sql)")"

  if [[ -n "$failures" ]]; then
    cat >&2 <<EOF
Postgres schema preflight failed.

The generated full import bundle is UUID-based, but the target database still
has missing or integer/serial columns. This is the same class of issue as
companies.id/users.id/leasing_companies.id having nextval(...) defaults.

Failing columns:
${failures}

Reset the target schema explicitly, then rerun the loader:
  FULL_IMPORT_ALLOW_SCHEMA_RESET=true ${SCRIPT_DIR}/reset_postgres_schema_via_tunnel.sh --env "$ENV_FILE" --yes
  ${0} --env "$ENV_FILE" --yes
EOF
    exit 1
  fi

  echo "Postgres UUID schema preflight passed."
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

require_command psql

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

if [[ "$PREFLIGHT_ONLY" == "true" ]]; then
  echo "Target: ${FULL_IMPORT_TARGET_LABEL}"
  echo "Postgres: ${PGUSER}@${PGHOST}:${PGPORT}/${PGDATABASE}"
  run_schema_preflight
  exit 0
fi

if [[ "${FULL_IMPORT_ALLOW_DESTRUCTIVE:-false}" != "true" || "$YES" != "true" ]]; then
  cat >&2 <<EOF
Refusing destructive Postgres full import.

Set FULL_IMPORT_ALLOW_DESTRUCTIVE=true in:
  $ENV_FILE

Then run with:
  $0 --env "$ENV_FILE" --yes
EOF
  exit 1
fi

require_command pg_dump
require_var FULL_IMPORT_BUNDLE_DIR

POSTGRES_LOAD_SQL="${POSTGRES_LOAD_SQL:-}"
if [[ -z "$POSTGRES_LOAD_SQL" ]]; then
  POSTGRES_LOAD_SQL="${FULL_IMPORT_BUNDLE_DIR}/postgres/load.sql"
fi

if [[ ! -f "$POSTGRES_LOAD_SQL" ]]; then
  echo "Postgres load SQL not found: $POSTGRES_LOAD_SQL" >&2
  exit 1
fi

if ! grep -q "TRUNCATE TABLE" "$POSTGRES_LOAD_SQL"; then
  echo "Postgres load SQL does not contain expected TRUNCATE TABLE guard: $POSTGRES_LOAD_SQL" >&2
  exit 1
fi

echo "Target: ${FULL_IMPORT_TARGET_LABEL}"
echo "Postgres: ${PGUSER}@${PGHOST}:${PGPORT}/${PGDATABASE}"
echo "SQL: ${POSTGRES_LOAD_SQL}"

run_schema_preflight

echo "Checking Postgres connectivity and current counts..."
PGPASSWORD="$PGPASSWORD" "${psql_cmd[@]}" -Atc "
SELECT 'database=' || current_database();
SELECT 'users_before=' || count(*) FROM users;
SELECT 'companies_before=' || count(*) FROM companies;
SELECT 'vehicles_before=' || count(*) FROM vehicles;
SELECT 'leasing_applications_before=' || count(*) FROM leasing_applications;
"

if [[ "${FULL_IMPORT_PG_BACKUP:-true}" == "true" ]]; then
  backup_dir="${FULL_IMPORT_BACKUP_DIR:-${FULL_IMPORT_BUNDLE_DIR}/backups}"
  mkdir -p "$backup_dir"
  backup_file="${backup_dir}/pg_${PGDATABASE}_before_full_import_$(date +%Y%m%d_%H%M%S).dump"
  echo "Creating Postgres backup: ${backup_file}"
  PGPASSWORD="$PGPASSWORD" pg_dump \
    -h "$PGHOST" \
    -p "$PGPORT" \
    -U "$PGUSER" \
    -d "$PGDATABASE" \
    -Fc \
    -f "$backup_file"
else
  echo "Skipping Postgres backup because FULL_IMPORT_PG_BACKUP=false"
fi

echo "Running destructive Postgres full import..."
PGPASSWORD="$PGPASSWORD" "${psql_cmd[@]}" -f "$POSTGRES_LOAD_SQL"

echo "Postgres counts after import:"
PGPASSWORD="$PGPASSWORD" "${psql_cmd[@]}" -Atc "
SELECT 'users=' || count(*) FROM users
UNION ALL SELECT 'companies=' || count(*) FROM companies
UNION ALL SELECT 'cities=' || count(*) FROM cities
UNION ALL SELECT 'warehouses=' || count(*) FROM warehouses
UNION ALL SELECT 'vehicles=' || count(*) FROM vehicles
UNION ALL SELECT 'vehicle_warehouses=' || count(*) FROM vehicle_warehouses
UNION ALL SELECT 'leasing_applications=' || count(*) FROM leasing_applications
UNION ALL SELECT 'leasing_company_applications=' || count(*) FROM leasing_company_applications
UNION ALL SELECT 'application_vehicles=' || count(*) FROM application_vehicles
UNION ALL SELECT 'exchange_requests=' || count(*) FROM exchange_requests
UNION ALL SELECT 'exchange_bids=' || count(*) FROM exchange_bids
UNION ALL SELECT 'seed_login=' || count(*) FROM users WHERE phone = '+76660000001'
UNION ALL SELECT 'demo_companies=' || count(*) FROM companies
  WHERE name ILIKE '%Демо Автосалон%'
     OR name ILIKE '%Демо Дистрибьютор%'
     OR name ~ '^Дилерский Центр [0-9]+$';
"
