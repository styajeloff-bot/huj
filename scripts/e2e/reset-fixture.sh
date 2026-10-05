#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPOSITORY_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

for variable_name in E2E_NAMESPACE E2E_ARTIFACT_DIR E2E_MANIFEST E2E_AUTH_STATE_DIR; do
    if [[ -z "${!variable_name:-}" ]]; then
        echo "$variable_name is required by the E2E fixture reset" >&2
        exit 2
    fi
done

cd "$REPOSITORY_ROOT/backend"
uv run python scripts/seed_special_equipment_e2e.py \
    --apply \
    --namespace "$E2E_NAMESPACE" \
    --reset \
    --artifacts-dir "$E2E_ARTIFACT_DIR" \
    --auth-state-dir "$E2E_AUTH_STATE_DIR" \
    --manifest-path "$E2E_MANIFEST"
