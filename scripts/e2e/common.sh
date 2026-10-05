#!/usr/bin/env bash

set -euo pipefail

E2E_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
E2E_REPOSITORY_ROOT="$(cd "$E2E_SCRIPT_DIR/../.." && pwd)"

e2e_require_run_id() {
    local run_id="${E2E_RUN_ID:-}"
    if [[ -z "$run_id" ]]; then
        run_id="local-$(date -u +%Y%m%d%H%M%S)-$$"
    fi
    if [[ ! "$run_id" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]{0,62}$ ]]; then
        echo "E2E_RUN_ID must match [A-Za-z0-9][A-Za-z0-9_.-]{0,62}" >&2
        return 2
    fi
    E2E_RUN_ID="$run_id"
    E2E_RESOURCE_PREFIX="carcraft-e2e-$run_id"
    E2E_STATE_DIR="${E2E_STATE_DIR:-$E2E_REPOSITORY_ROOT/.e2e-runtime/$run_id}"
    E2E_STATE_FILE="$E2E_STATE_DIR/runtime.env"
    export E2E_RUN_ID E2E_RESOURCE_PREFIX E2E_STATE_DIR E2E_STATE_FILE
}

e2e_require_owned_state_dir() {
    local runtime_root="$E2E_REPOSITORY_ROOT/.e2e-runtime"
    local canonical_state_dir
    if ! canonical_state_dir="$(
        python3 - "$E2E_REPOSITORY_ROOT" "$runtime_root" \
            "$E2E_STATE_DIR" "$E2E_RUN_ID" <<'PY'
import os
import sys

repository_root = os.path.realpath(sys.argv[1])
runtime_path = os.path.abspath(sys.argv[2])
runtime_root = os.path.realpath(runtime_path)
requested_state_dir = os.path.abspath(sys.argv[3])
state_dir = os.path.realpath(requested_state_dir)
expected_state_dir = os.path.join(runtime_root, sys.argv[4])

try:
    runtime_is_owned = (
        runtime_root != repository_root
        and os.path.commonpath((repository_root, runtime_root)) == repository_root
    )
    state_is_owned = (
        state_dir != runtime_root
        and os.path.commonpath((runtime_root, state_dir)) == runtime_root
    )
except ValueError:
    runtime_is_owned = False
    state_is_owned = False

is_safe = (
    runtime_path == runtime_root
    and requested_state_dir == expected_state_dir
    and state_dir == expected_state_dir
    and runtime_is_owned
    and state_is_owned
)
if not is_safe:
    raise SystemExit(1)
print(state_dir)
PY
    )"; then
        echo "Refusing E2E state directory outside owned runtime path " \
            "$runtime_root/$E2E_RUN_ID: $E2E_STATE_DIR" >&2
        return 2
    fi
    E2E_STATE_DIR="$canonical_state_dir"
    E2E_STATE_FILE="$E2E_STATE_DIR/runtime.env"
    export E2E_STATE_DIR E2E_STATE_FILE
}

e2e_select_port() {
    local requested_port="${1:-0}"
    python3 - "$requested_port" <<'PY'
import socket
import sys

requested = int(sys.argv[1])
with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
    listener.bind(("127.0.0.1", requested))
    print(listener.getsockname()[1])
PY
}

e2e_select_ports() {
    python3 - "$@" <<'PY'
import socket
import sys

sockets = []
ports = []
try:
    for raw_value in sys.argv[1:]:
        requested = int(raw_value)
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.bind(("127.0.0.1", requested))
        sockets.append(listener)
        ports.append(listener.getsockname()[1])
    print(*ports)
finally:
    for listener in sockets:
        listener.close()
PY
}

e2e_write_state_value() {
    local key="$1"
    local value="$2"
    e2e_require_owned_state_dir
    printf '%s=%q\n' "$key" "$value" >>"$E2E_STATE_FILE"
}

e2e_prepare_private_state() {
    e2e_require_owned_state_dir
    mkdir -p "$E2E_STATE_DIR"
    chmod 700 "$E2E_STATE_DIR"
    : >"$E2E_STATE_FILE"
    chmod 600 "$E2E_STATE_FILE"
}

e2e_wait_for_command() {
    local label="$1"
    local timeout_seconds="$2"
    shift 2
    local deadline=$((SECONDS + timeout_seconds))
    until "$@" >/dev/null 2>&1; do
        if ((SECONDS >= deadline)); then
            echo "Timed out waiting for $label" >&2
            return 1
        fi
        sleep 1
    done
}

e2e_wait_for_http() {
    local label="$1"
    local url="$2"
    local timeout_seconds="${3:-60}"
    e2e_wait_for_command "$label" "$timeout_seconds" curl --fail --silent --show-error "$url"
}

e2e_process_start_time() {
    local pid="$1"
    LC_ALL=C ps -p "$pid" -o lstart= 2>/dev/null || true
}

e2e_render_nginx_config() {
    local template="$1"
    local output="$2"
    local nginx_port="$3"
    local backend_host="$4"
    local backend_port="$5"
    local frontend_host="$6"
    local frontend_port="$7"

    sed \
        -e "s/__NGINX_PORT__/$nginx_port/g" \
        -e "s/__BACKEND_HOST__/$backend_host/g" \
        -e "s/__BACKEND_PORT__/$backend_port/g" \
        -e "s/__FRONTEND_HOST__/$frontend_host/g" \
        -e "s/__FRONTEND_PORT__/$frontend_port/g" \
        "$template" >"$output"
}

e2e_source_state() {
    if [[ ! -f "$E2E_STATE_FILE" ]]; then
        echo "E2E runtime state does not exist: $E2E_STATE_FILE" >&2
        return 1
    fi
    # State is generated only by e2e_write_state_value with shell escaping.
    # shellcheck disable=SC1090
    source "$E2E_STATE_FILE"
}
