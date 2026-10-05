#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPOSITORY_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
ARTIFACT_DIR="${E2E_ARTIFACT_DIR:-$REPOSITORY_ROOT/artifacts/e2e}"

if [[ "${1:-}" == "--print-plan" ]]; then
    printf '%s\n' \
        "migrate database to 085" \
        "seed legacy 085 rows" \
        "migrate database to head" \
        "verify category=false and cart quantity=1 at head" \
        "retain legacy rows for full-stack smoke"
    exit 0
fi
if (($#)); then
    echo "Usage: bash scripts/e2e/verify-backfill.sh [--print-plan]" >&2
    exit 2
fi

if [[ -z "${DATABASE_URL:-}" ]]; then
    echo "DATABASE_URL is required for the 085 -> 086 backfill check" >&2
    exit 2
fi

cd "$REPOSITORY_ROOT/backend"
uv run alembic upgrade 085
uv run python "$SCRIPT_DIR/backfill_21954.py" seed
uv run alembic upgrade head
uv run python "$SCRIPT_DIR/backfill_21954.py" verify \
    --artifact "$ARTIFACT_DIR/backfill-21954.json"
