#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

PRINT_PLAN=false
while (($#)); do
    case "$1" in
        --print-plan)
            PRINT_PLAN=true
            shift
            ;;
        --state-dir)
            if (($# < 2)); then
                echo "--state-dir requires a value" >&2
                exit 2
            fi
            E2E_STATE_DIR="$2"
            shift 2
            ;;
        *)
            echo "Usage: bash scripts/e2e/cleanup.sh [--state-dir PATH] [--print-plan]" >&2
            exit 2
            ;;
    esac
done

e2e_require_run_id

POSTGRES_CONTAINER="$E2E_RESOURCE_PREFIX-postgres"
REDIS_CONTAINER="$E2E_RESOURCE_PREFIX-redis"
REDPANDA_CONTAINER="$E2E_RESOURCE_PREFIX-redpanda"
NGINX_CONTAINER="$E2E_RESOURCE_PREFIX-nginx"
E2E_NETWORK="$E2E_RESOURCE_PREFIX-net"

print_plan() {
    printf '%s\n' \
        "stop host processes for $E2E_RUN_ID" \
        "remove generated frontend test-results" \
        "remove generated frontend playwright-report" \
        "remove container $NGINX_CONTAINER" \
        "remove container $REDPANDA_CONTAINER" \
        "remove container $REDIS_CONTAINER" \
        "remove container $POSTGRES_CONTAINER" \
        "remove network $E2E_NETWORK" \
        "remove runtime state for $E2E_RUN_ID"
}

if [[ "$PRINT_PLAN" == true ]]; then
    print_plan
    exit 0
fi

e2e_require_owned_state_dir

stop_pid_file() {
    local pid_file="$1"
    local start_time_file="${pid_file%.pid}.start-time"
    [[ -f "$pid_file" ]] || return 0
    local pid
    pid="$(<"$pid_file")"
    if [[ ! "$pid" =~ ^[0-9]+$ ]] || ((pid <= 1)); then
        echo "Ignoring invalid E2E pid file: $pid_file" >&2
        return 0
    fi
    if ! kill -0 "$pid" 2>/dev/null; then
        return 0
    fi
    if [[ ! -f "$start_time_file" ]]; then
        echo "Ignoring unowned E2E pid without start-time marker: $pid_file" >&2
        return 0
    fi
    local expected_start_time
    expected_start_time="$(<"$start_time_file")"
    local actual_start_time
    actual_start_time="$(e2e_process_start_time "$pid")"
    if [[ -z "$expected_start_time" || "$actual_start_time" != "$expected_start_time" ]]; then
        echo "Ignoring reused or unowned E2E pid: $pid" >&2
        return 0
    fi
    kill -TERM "$pid" 2>/dev/null || true
    local deadline=$((SECONDS + 10))
    while [[ "$(e2e_process_start_time "$pid")" == "$expected_start_time" ]] \
        && ((SECONDS < deadline)); do
        sleep 1
    done
    if [[ "$(e2e_process_start_time "$pid")" == "$expected_start_time" ]]; then
        kill -KILL "$pid" 2>/dev/null || true
    fi
}

for process_name in nginx frontend taskiq backend; do
    stop_pid_file "$E2E_STATE_DIR/$process_name.pid"
done

if [[ "${E2E_PRESERVE_FRONTEND_ARTIFACTS:-false}" != true ]]; then
    rm -rf \
        "$E2E_REPOSITORY_ROOT/frontend/test-results" \
        "$E2E_REPOSITORY_ROOT/frontend/playwright-report"
fi

if command -v docker >/dev/null; then
    for container in \
        "$NGINX_CONTAINER" \
        "$REDPANDA_CONTAINER" \
        "$REDIS_CONTAINER" \
        "$POSTGRES_CONTAINER"; do
        docker rm --force "$container" >/dev/null 2>&1 || true
    done
    docker network rm "$E2E_NETWORK" >/dev/null 2>&1 || true
fi

rm -rf -- "$E2E_STATE_DIR"
