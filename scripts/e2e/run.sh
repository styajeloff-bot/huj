#!/usr/bin/env bash

set -euo pipefail

# The document registry suite owns an isolated stack and its full API/browser/worker gates.
if [[ "${1:-}" == "--suite" ]]; then
    case "${2:-}" in
        warehouse-form) shift 2; exec bash "$(dirname "${BASH_SOURCE[0]}")/warehouse-form/run.sh" "$@" ;;
        22406) shift 2; exec bash "$(dirname "${BASH_SOURCE[0]}")/22406/run.sh" "$@" ;;
        22296) shift 2; exec bash "$(dirname "${BASH_SOURCE[0]}")/22296/run.sh" "$@" ;;
        22398) shift 2; exec bash "$(dirname "${BASH_SOURCE[0]}")/22398/run.sh" "$@" ;;
        22286) shift 2; exec bash "$(dirname "${BASH_SOURCE[0]}")/22286/run.sh" "$@" ;;
    esac
    echo "Usage: bash scripts/e2e/run.sh --suite {22296|22286|22398|22406|warehouse-form}" >&2
    exit 2
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

CI_MODE=false
PRINT_PLAN=false
PRINT_ENVIRONMENT_CONTRACT=false
PRINT_PROCESS_CONTRACT=false
KEEP_RUNTIME=false
while (($#)); do
    case "$1" in
        --ci)
            CI_MODE=true
            shift
            ;;
        --print-plan)
            PRINT_PLAN=true
            shift
            ;;
        --print-environment-contract)
            PRINT_ENVIRONMENT_CONTRACT=true
            shift
            ;;
        --print-process-contract)
            PRINT_PROCESS_CONTRACT=true
            shift
            ;;
        --keep)
            KEEP_RUNTIME=true
            shift
            ;;
        *)
            echo "Usage: bash scripts/e2e/run.sh [--ci] [--keep] [--print-plan] [--print-environment-contract] [--print-process-contract]" >&2
            exit 2
            ;;
    esac
done

e2e_require_run_id
E2E_NAMESPACE="$E2E_RUN_ID"
E2E_FIXTURE_RESET_COMMAND="/bin/bash $SCRIPT_DIR/reset-fixture.sh"
export E2E_FIXTURE_RESET_COMMAND E2E_NAMESPACE

if [[ "$PRINT_ENVIRONMENT_CONTRACT" == true ]]; then
    printf '%s\n' \
        "E2E_FIXTURE_RESET_COMMAND=$E2E_FIXTURE_RESET_COMMAND" \
        "E2E_FIXTURE_MANIFEST mirrors E2E_MANIFEST" \
        "E2E_NAMESPACE=E2E_RUN_ID for every fixture reset"
    exit 0
fi

if [[ "$PRINT_PROCESS_CONTRACT" == true ]]; then
    printf '%s\n' \
        "Taskiq=uv run taskiq worker --log-level INFO --log-format %(message)s infrastructure.taskiq_broker:broker application.tasks"
    exit 0
fi

print_plan() {
    printf '%s\n' \
        "prepare artifacts" \
        "health PostgreSQL" \
        "health Redis" \
        "health Redpanda" \
        "health S3 and bucket" \
        "generate ES256 keys" \
        "verify migration 085 -> head" \
        "migrate database to head" \
        "start FastAPI" \
        "start Taskiq worker" \
        "build Nuxt" \
        "start Nuxt" \
        "start Nginx" \
        "health FastAPI" \
        "health Taskiq worker" \
        "health Nuxt" \
        "health Nginx public API" \
        "test migrated legacy catalog full-stack" \
        "remove migrated legacy rows" \
        "apply E2E fixture $E2E_NAMESPACE" \
        "test traceability guard desktop-chromium" \
        "test 21940 desktop-chromium" \
        "reset fixture $E2E_NAMESPACE before 21954 desktop-chromium" \
        "test 21954 desktop-chromium" \
        "reset fixture $E2E_NAMESPACE before 21984 desktop-chromium" \
        "test 21984 desktop-chromium" \
        "reset fixture $E2E_NAMESPACE before 22098 desktop-chromium" \
        "test 22098 desktop-chromium" \
        "reset fixture $E2E_NAMESPACE before 22130 desktop-chromium" \
        "test 22130 desktop-chromium" \
        "reset fixture $E2E_NAMESPACE before 22282 desktop-chromium" \
        "test 22282 desktop-chromium" \
        "reset fixture $E2E_NAMESPACE before 22294 desktop-chromium" \
        "test 22294 desktop-chromium" \
        "reset fixture $E2E_NAMESPACE before 22370 desktop-chromium" \
        "test 22370 desktop-chromium" \
        "reset fixture $E2E_NAMESPACE before 22386 desktop-chromium" \
        "prepare compact-card fixture 22386" \
        "test 22386 desktop-chromium" \
        "restore compact-card fixture 22386 before the next reset, including failures" \
        "reset fixture $E2E_NAMESPACE before warehouses-adjustments desktop-chromium" \
        "test warehouses-adjustments desktop-chromium" \
        "collect logs and artifacts"
}

if [[ "$PRINT_PLAN" == true ]]; then
    print_plan
    exit 0
fi

for executable in curl uv bun python3; do
    command -v "$executable" >/dev/null || {
        echo "$executable is required by the E2E runner" >&2
        exit 1
    }
done

e2e_require_owned_state_dir

if [[ "$CI_MODE" == false ]]; then
    bash "$SCRIPT_DIR/provision.sh"
    e2e_source_state
else
    mkdir -p "$E2E_STATE_DIR"
    E2E_POSTGRES_HOST="${E2E_POSTGRES_HOST:-postgres}"
    E2E_POSTGRES_PORT="${E2E_POSTGRES_PORT:-5432}"
    E2E_POSTGRES_USER="${E2E_POSTGRES_USER:-carcraft_e2e}"
    E2E_POSTGRES_PASSWORD="${E2E_POSTGRES_PASSWORD:-carcraft_e2e}"
    E2E_POSTGRES_DB="${E2E_POSTGRES_DB:-carcraft_e2e}"
    E2E_REDIS_HOST="${E2E_REDIS_HOST:-redis}"
    E2E_REDIS_PORT="${E2E_REDIS_PORT:-6379}"
    E2E_KAFKA_HOST="${E2E_KAFKA_HOST:-redpanda}"
    E2E_KAFKA_PORT="${E2E_KAFKA_PORT:-9092}"
    E2E_BACKEND_HOST=127.0.0.1
    E2E_BACKEND_PORT="${E2E_BACKEND_PORT:-3002}"
    E2E_FRONTEND_HOST=127.0.0.1
    E2E_FRONTEND_PORT="${E2E_FRONTEND_PORT:-3000}"
    E2E_NGINX_HOST=127.0.0.1
    E2E_NGINX_PORT="${E2E_NGINX_PORT:-8080}"
fi

E2E_ARTIFACT_DIR="${E2E_ARTIFACT_DIR:-$E2E_REPOSITORY_ROOT/artifacts/e2e/$E2E_RUN_ID}"
E2E_MANIFEST="${E2E_MANIFEST:-$E2E_ARTIFACT_DIR/fixture-manifest.json}"
E2E_FIXTURE_MANIFEST="$E2E_MANIFEST"
E2E_LOG_DIR="$E2E_STATE_DIR/logs"
JWT_KEYS_DIR="$E2E_STATE_DIR/jwt-keys"
E2E_AUTH_STATE_DIR="$E2E_STATE_DIR/auth"
E2E_EMPLOYEE_STORAGE_STATE="$E2E_AUTH_STATE_DIR/employee-storage-state.json"
E2E_CLIENT_STORAGE_STATE="$E2E_AUTH_STATE_DIR/client-storage-state.json"
E2E_CLIENT_NON_OWNER_STORAGE_STATE="$E2E_AUTH_STATE_DIR/client-non-owner-storage-state.json"
PUBLIC_URL="http://$E2E_NGINX_HOST:$E2E_NGINX_PORT"
BACKEND_URL="http://$E2E_BACKEND_HOST:$E2E_BACKEND_PORT"
FRONTEND_URL="http://$E2E_FRONTEND_HOST:$E2E_FRONTEND_PORT"
APP_URL="$PUBLIC_URL"
if [[ "$CI_MODE" == false ]]; then
    APP_URL="$FRONTEND_URL"
fi

mkdir -p "$E2E_ARTIFACT_DIR" "$E2E_LOG_DIR" "$JWT_KEYS_DIR" "$E2E_AUTH_STATE_DIR"
chmod 700 "$E2E_AUTH_STATE_DIR"

export \
    E2E_ARTIFACT_DIR \
    E2E_MANIFEST \
    E2E_FIXTURE_MANIFEST \
    E2E_AUTH_STATE_DIR \
    E2E_EMPLOYEE_STORAGE_STATE \
    E2E_CLIENT_STORAGE_STATE \
    E2E_CLIENT_NON_OWNER_STORAGE_STATE \
    E2E_BASE_URL="$PUBLIC_URL" \
    E2E_APP_BASE_URL="$APP_URL" \
    DATABASE_URL="postgresql://$E2E_POSTGRES_USER:$E2E_POSTGRES_PASSWORD@$E2E_POSTGRES_HOST:$E2E_POSTGRES_PORT/$E2E_POSTGRES_DB" \
    REDIS_URL="redis://$E2E_REDIS_HOST:$E2E_REDIS_PORT/0" \
    KAFKA_BROKERS="$E2E_KAFKA_HOST:$E2E_KAFKA_PORT" \
    S3_ENDPOINT="${S3_ENDPOINT:-https://storage.yandexcloud.net}" \
    S3_REGION="${S3_REGION:-ru-central1}" \
    S3_BUCKET="${S3_BUCKET:-multileasing}" \
    S3_ACCESS_KEY_ID="${S3_ACCESS_KEY_ID:-}" \
    S3_SECRET_ACCESS_KEY="${S3_SECRET_ACCESS_KEY:-}" \
    S3_PUBLIC_BASE_URL="${S3_PUBLIC_BASE_URL:-}" \
    JWT_KEYS_DIR \
    PUBLIC_URL \
    API_URL="$PUBLIC_URL/api/v1" \
    NUXT_API_INTERNAL_BASE="$PUBLIC_URL" \
    COOKIE_SECURE=false \
    COOKIE_SAMESITE=lax \
    CORS_ALLOWED_ORIGINS="$PUBLIC_URL,$APP_URL" \
    RATE_LIMIT_ENABLED=false \
    CSRF_ENABLED=false \
    MOBILE_ID_ENABLED=false \
    NUXT_PUBLIC_API_BASE="$PUBLIC_URL" \
    NUXT_PUBLIC_YANDEX_METRIKA_ENABLED=false \
    NUXT_PUBLIC_VERBOX_ENABLED=false

collect_diagnostics() {
    local exit_status="$1"
    mkdir -p "$E2E_ARTIFACT_DIR/logs"
    printf '%s\n' "$exit_status" >"$E2E_ARTIFACT_DIR/exit-status.txt"
    for log_file in "$E2E_LOG_DIR"/*.log; do
        [[ -f "$log_file" ]] || continue
        cp "$log_file" "$E2E_ARTIFACT_DIR/logs/"
    done
    if [[ "$CI_MODE" == false ]] && command -v docker >/dev/null; then
        for service in postgres redis redpanda nginx; do
            docker logs "$E2E_RESOURCE_PREFIX-$service" \
                >"$E2E_ARTIFACT_DIR/logs/$service.log" 2>&1 || true
        done
    fi
    if [[ -d "$E2E_REPOSITORY_ROOT/frontend/playwright-report" ]]; then
        cp -R "$E2E_REPOSITORY_ROOT/frontend/playwright-report" \
            "$E2E_ARTIFACT_DIR/playwright-report" || true
    fi
    if [[ -d "$E2E_REPOSITORY_ROOT/frontend/test-results" ]]; then
        cp -R "$E2E_REPOSITORY_ROOT/frontend/test-results" \
            "$E2E_ARTIFACT_DIR/test-results" || true
    fi
}

remove_auth_states() {
    python3 - \
        "$E2E_AUTH_STATE_DIR" \
        "$E2E_EMPLOYEE_STORAGE_STATE" \
        "$E2E_CLIENT_STORAGE_STATE" <<'PY'
import sys
from pathlib import Path

auth_root = Path(sys.argv[1]).resolve()
for raw_path in sys.argv[2:]:
    state_path = Path(raw_path).resolve()
    if state_path.parent != auth_root:
        raise SystemExit(f"Refusing to remove auth state outside {auth_root}: {state_path}")
    state_path.unlink(missing_ok=True)
try:
    auth_root.rmdir()
except OSError:
    pass
PY
}

compact_card_fixture_prepared=false
cleanup_compact_card_fixture() {
    if [[ "$compact_card_fixture_prepared" != true ]]; then
        return 0
    fi
    (
        cd "$E2E_REPOSITORY_ROOT/backend" || exit "$?"
        uv run python "$SCRIPT_DIR/22386/prepare.py" --cleanup
    ) || return "$?"
    compact_card_fixture_prepared=false
}

finish() {
    local exit_status=$?
    trap - EXIT INT TERM
    if ! cleanup_compact_card_fixture; then
        echo "Failed to restore compact-card fixture 22386" >&2
        if [[ "$exit_status" == 0 ]]; then
            exit_status=1
        fi
    fi
    remove_auth_states || true
    collect_diagnostics "$exit_status" || true
    if [[ "$KEEP_RUNTIME" == false ]]; then
        E2E_RUN_ID="$E2E_RUN_ID" \
            E2E_STATE_DIR="$E2E_STATE_DIR" \
            E2E_PRESERVE_FRONTEND_ARTIFACTS="$CI_MODE" \
            bash "$SCRIPT_DIR/cleanup.sh" || true
    fi
    exit "$exit_status"
}
trap finish EXIT INT TERM

start_process() {
    local name="$1"
    local working_directory="$2"
    shift 2
    (
        cd "$working_directory"
        exec "$@"
    ) >"$E2E_LOG_DIR/$name.log" 2>&1 &
    local process_pid=$!
    local start_time
    start_time="$(e2e_process_start_time "$process_pid")"
    if [[ -z "$start_time" ]]; then
        echo "Unable to capture start time for E2E process $name ($process_pid)" >&2
        kill -TERM "$process_pid" 2>/dev/null || true
        return 1
    fi
    printf '%s\n' "$process_pid" >"$E2E_STATE_DIR/$name.pid"
    printf '%s\n' "$start_time" >"$E2E_STATE_DIR/$name.start-time"
}

(
    cd "$E2E_REPOSITORY_ROOT/backend"
    uv run python "$SCRIPT_DIR/check_dependencies.py"
) >"$E2E_LOG_DIR/dependencies.log" 2>&1

apply_fixture() {
    cleanup_compact_card_fixture
    /bin/bash "$SCRIPT_DIR/reset-fixture.sh"
}

prepare_auth_states() {
    local employee_args=( \
        --manifest "$E2E_MANIFEST" \
        --role employee \
        --base-url "$PUBLIC_URL" \
        --output "$E2E_EMPLOYEE_STORAGE_STATE" \
    )
    if [[ -n "${E2E_EMPLOYEE_PHONE:-}" ]]; then
        employee_args+=(--phone "$E2E_EMPLOYEE_PHONE")
    fi
    python3 "$SCRIPT_DIR/auth_state.py" "${employee_args[@]}"

    local client_args=( \
        --manifest "$E2E_MANIFEST" \
        --role client \
        --base-url "$PUBLIC_URL" \
        --output "$E2E_CLIENT_STORAGE_STATE" \
    )
    if [[ -n "${E2E_CLIENT_PHONE:-}" ]]; then
        client_args+=(--phone "$E2E_CLIENT_PHONE")
    fi
    python3 "$SCRIPT_DIR/auth_state.py" "${client_args[@]}"

    python3 "$SCRIPT_DIR/auth_state.py" \
        --manifest "$E2E_MANIFEST" \
        --role client_non_owner \
        --base-url "$PUBLIC_URL" \
        --output "$E2E_CLIENT_NON_OWNER_STORAGE_STATE"
}

bash "$E2E_REPOSITORY_ROOT/backend/scripts/generate-jwt-keys.sh" "$JWT_KEYS_DIR" \
    >"$E2E_LOG_DIR/jwt-keys.log"

if [[ -n "${E2E_BACKFILL_COMMAND:-}" ]]; then
    bash -lc "$E2E_BACKFILL_COMMAND"
else
    bash "$SCRIPT_DIR/verify-backfill.sh"
fi

(
    cd "$E2E_REPOSITORY_ROOT/backend"
    uv run alembic upgrade head
)

start_process backend "$E2E_REPOSITORY_ROOT/backend" \
    uv run uvicorn main:app \
    --host "$E2E_BACKEND_HOST" --port "$E2E_BACKEND_PORT" \
    --proxy-headers --forwarded-allow-ips 127.0.0.1
start_process taskiq "$E2E_REPOSITORY_ROOT/backend" \
    uv run taskiq worker --log-level INFO --log-format "%(message)s" \
    infrastructure.taskiq_broker:broker application.tasks

(
    cd "$E2E_REPOSITORY_ROOT/frontend"
    bun run build:frontend
) >"$E2E_LOG_DIR/frontend-build.log" 2>&1
start_process frontend "$E2E_REPOSITORY_ROOT/frontend" \
    env HOST="$E2E_FRONTEND_HOST" PORT="$E2E_FRONTEND_PORT" \
    node .output/server/index.mjs

if [[ "$CI_MODE" == true ]]; then
    command -v nginx >/dev/null || {
        echo "nginx must be installed in the CI job image" >&2
        exit 1
    }
    E2E_NGINX_CONFIG="$E2E_STATE_DIR/nginx.conf"
    e2e_render_nginx_config \
        "$SCRIPT_DIR/nginx.conf.template" "$E2E_NGINX_CONFIG" \
        "$E2E_NGINX_PORT" \
        "$E2E_BACKEND_HOST" "$E2E_BACKEND_PORT" \
        "$E2E_FRONTEND_HOST" "$E2E_FRONTEND_PORT"
    nginx -t -c "$E2E_NGINX_CONFIG"
    start_process nginx "$E2E_REPOSITORY_ROOT" \
        nginx -c "$E2E_NGINX_CONFIG" -g "daemon off;"
fi

e2e_wait_for_http FastAPI "$BACKEND_URL/api/v1/health" 120
e2e_wait_for_command "Taskiq worker" 60 \
    grep -Eq "Listening started|receiver.*started|taskiq.*started" \
    "$E2E_LOG_DIR/taskiq.log"
e2e_wait_for_http Nuxt "$FRONTEND_URL" 180
e2e_wait_for_http "Nginx public API" "$PUBLIC_URL/api/v1/health" 60

export E2E_BACKFILL_SMOKE=true
export PLAYWRIGHT_JUNIT_OUTPUT_NAME="$E2E_ARTIFACT_DIR/junit-21954-backfill-smoke.xml"
(
    cd "$E2E_REPOSITORY_ROOT/frontend"
    bun x playwright test \
        "tests/e2e/special-equipment/21954-backfill.smoke.spec.ts" \
        --project=desktop-chromium
)
unset E2E_BACKFILL_SMOKE

(
    cd "$E2E_REPOSITORY_ROOT/backend"
    uv run python "$SCRIPT_DIR/backfill_21954.py" cleanup
)

apply_fixture
prepare_auth_states

for project in desktop-chromium; do
    export PLAYWRIGHT_JUNIT_OUTPUT_NAME="$E2E_ARTIFACT_DIR/junit-traceability-$project.xml"
    (
        cd "$E2E_REPOSITORY_ROOT/frontend"
        bun x playwright test \
            "tests/e2e/special-equipment/traceability.guard.spec.ts" \
            --project="$project"
    )
done

spec_file_for_suite() {
    case "$1" in
        21940) printf '%s\n' "tests/e2e/special-equipment/21940-catalog-corrections.spec.ts" ;;
        21954) printf '%s\n' "tests/e2e/special-equipment/21954-attachments.spec.ts" ;;
        21984) printf '%s\n' "tests/e2e/special-equipment/21984-homepage-catalog.spec.ts" ;;
        22098) printf '%s\n' "tests/e2e/special-equipment/22098-v5-16.spec.ts" ;;
        22130) printf '%s\n' "tests/e2e/(models|workspace)/22130-.*\\.spec\\.ts" ;;
        22282) printf '%s\n' "tests/e2e/checkout/22282-(cart-cleanup-at-draft|auto-switch-status-steps)\\.spec\\.ts" ;;
        22294) printf '%s\n' "tests/e2e/workspace/22294-company-admin-edit.spec.ts" ;;
        22370) printf '%s\n' "tests/e2e/checkout/22370-special-equipment-grouping.spec.ts" ;;
        22386) printf '%s\n' "tests/e2e/special-equipment/22386-compact-vehicle.spec.ts" ;;
        se-attachment-category-under-ordinary) printf '%s\n' "tests/e2e/special-equipment/se-attachment-category-under-ordinary.spec.ts" ;;
        se-kits) printf '%s\n' "tests/e2e/special-equipment/se-kits.spec.ts" ;;
        se-units) printf '%s\n' "tests/e2e/special-equipment/se-units.spec.ts" ;;
        warehouses-adjustments) printf '%s\n' "tests/e2e/workspace/warehouses-adjustments.spec.ts" ;;
        *)
            echo "Unknown E2E suite: $1" >&2
            return 2
            ;;
    esac
}

first_project=true
read -r -a acceptance_suites <<<"${E2E_ACCEPTANCE_SUITES:-21940 21954 21984 22098 22130 22282 22294 22370 22386 se-kits se-units warehouses-adjustments}"
for suite in "${acceptance_suites[@]}"; do
    for project in desktop-chromium; do
        if [[ "$first_project" == false ]]; then
            apply_fixture
            prepare_auth_states
        fi
        if [[ "$suite" == "22386" ]]; then
            (cd "$E2E_REPOSITORY_ROOT/backend" && uv run python "$SCRIPT_DIR/22386/prepare.py")
            compact_card_fixture_prepared=true
        fi
        first_project=false
        export PLAYWRIGHT_JUNIT_OUTPUT_NAME="$E2E_ARTIFACT_DIR/junit-$suite-$project.xml"
        spec_file="$(spec_file_for_suite "$suite")"
        playwright_args=("$spec_file" "--project=$project")
        if [[ "$suite" == "22130" ]]; then
            playwright_args+=(--workers=1)
        fi
        (
            cd "$E2E_REPOSITORY_ROOT/frontend"
            bun x playwright test "${playwright_args[@]}"
        )
        cleanup_compact_card_fixture
    done
done
