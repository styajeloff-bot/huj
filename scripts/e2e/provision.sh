#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

PRINT_PLAN=false
if [[ "${1:-}" == "--print-plan" ]]; then
    PRINT_PLAN=true
    shift
fi
if (($#)); then
    echo "Usage: bash scripts/e2e/provision.sh [--print-plan]" >&2
    exit 2
fi

e2e_require_run_id

POSTGRES_CONTAINER="$E2E_RESOURCE_PREFIX-postgres"
REDIS_CONTAINER="$E2E_RESOURCE_PREFIX-redis"
REDPANDA_CONTAINER="$E2E_RESOURCE_PREFIX-redpanda"
NGINX_CONTAINER="$E2E_RESOURCE_PREFIX-nginx"
E2E_NETWORK="$E2E_RESOURCE_PREFIX-net"

print_plan() {
    printf '%s\n' \
        "provision network $E2E_NETWORK" \
        "provision postgres $POSTGRES_CONTAINER" \
        "provision redis $REDIS_CONTAINER" \
        "provision redpanda $REDPANDA_CONTAINER" \
        "health postgres" \
        "health redis" \
        "health redpanda" \
        "render nginx config" \
        "validate nginx config" \
        "provision nginx $NGINX_CONTAINER" \
        "write runtime state"
}

if [[ "$PRINT_PLAN" == true ]]; then
    print_plan
    exit 0
fi

e2e_require_owned_state_dir

command -v docker >/dev/null || {
    echo "docker is required for local E2E provisioning" >&2
    exit 1
}
command -v curl >/dev/null || {
    echo "curl is required for local E2E provisioning" >&2
    exit 1
}

read -r \
    POSTGRES_PORT \
    REDIS_PORT \
    KAFKA_PORT \
    NGINX_PORT \
    BACKEND_PORT \
    FRONTEND_PORT \
    < <(
        e2e_select_ports \
            "${E2E_POSTGRES_PORT:-0}" \
            "${E2E_REDIS_PORT:-0}" \
            "${E2E_KAFKA_PORT:-0}" \
            "${E2E_NGINX_PORT:-0}" \
            "${E2E_BACKEND_PORT:-0}" \
            "${E2E_FRONTEND_PORT:-0}"
    )

POSTGRES_USER="${E2E_POSTGRES_USER:-carcraft_e2e}"
POSTGRES_PASSWORD="${E2E_POSTGRES_PASSWORD:-carcraft_e2e}"
POSTGRES_DB="${E2E_POSTGRES_DB:-carcraft_e2e}"

POSTGRES_IMAGE="${E2E_POSTGRES_IMAGE:-postgres:16-alpine}"
REDIS_IMAGE="${E2E_REDIS_IMAGE:-redis:7-alpine}"
REDPANDA_IMAGE="${E2E_REDPANDA_IMAGE:-redpandadata/redpanda:v24.3.5}"
NGINX_IMAGE="${E2E_NGINX_IMAGE:-nginx:1.27-alpine}"

e2e_prepare_private_state
e2e_write_state_value E2E_RUN_ID "$E2E_RUN_ID"
e2e_write_state_value E2E_RESOURCE_PREFIX "$E2E_RESOURCE_PREFIX"
e2e_write_state_value E2E_NETWORK "$E2E_NETWORK"
e2e_write_state_value E2E_POSTGRES_CONTAINER "$POSTGRES_CONTAINER"
e2e_write_state_value E2E_REDIS_CONTAINER "$REDIS_CONTAINER"
e2e_write_state_value E2E_REDPANDA_CONTAINER "$REDPANDA_CONTAINER"
e2e_write_state_value E2E_NGINX_CONTAINER "$NGINX_CONTAINER"
e2e_write_state_value E2E_POSTGRES_HOST 127.0.0.1
e2e_write_state_value E2E_POSTGRES_PORT "$POSTGRES_PORT"
e2e_write_state_value E2E_POSTGRES_USER "$POSTGRES_USER"
e2e_write_state_value E2E_POSTGRES_PASSWORD "$POSTGRES_PASSWORD"
e2e_write_state_value E2E_POSTGRES_DB "$POSTGRES_DB"
e2e_write_state_value E2E_REDIS_HOST 127.0.0.1
e2e_write_state_value E2E_REDIS_PORT "$REDIS_PORT"
e2e_write_state_value E2E_KAFKA_HOST 127.0.0.1
e2e_write_state_value E2E_KAFKA_PORT "$KAFKA_PORT"
e2e_write_state_value E2E_NGINX_HOST 127.0.0.1
e2e_write_state_value E2E_NGINX_PORT "$NGINX_PORT"
e2e_write_state_value E2E_BACKEND_HOST 127.0.0.1
e2e_write_state_value E2E_BACKEND_PORT "$BACKEND_PORT"
e2e_write_state_value E2E_FRONTEND_HOST 127.0.0.1
e2e_write_state_value E2E_FRONTEND_PORT "$FRONTEND_PORT"

cleanup_on_failure() {
    local status=$?
    if ((status != 0)); then
        bash "$SCRIPT_DIR/cleanup.sh" --state-dir "$E2E_STATE_DIR" >/dev/null 2>&1 || true
    fi
    exit "$status"
}
trap cleanup_on_failure EXIT

docker network create "$E2E_NETWORK" >/dev/null

docker run --detach --name "$POSTGRES_CONTAINER" --network "$E2E_NETWORK" \
    --publish "127.0.0.1:$POSTGRES_PORT:5432" \
    --env "POSTGRES_USER=$POSTGRES_USER" \
    --env "POSTGRES_PASSWORD=$POSTGRES_PASSWORD" \
    --env "POSTGRES_DB=$POSTGRES_DB" \
    "$POSTGRES_IMAGE" >/dev/null

docker run --detach --name "$REDIS_CONTAINER" --network "$E2E_NETWORK" \
    --publish "127.0.0.1:$REDIS_PORT:6379" \
    "$REDIS_IMAGE" redis-server --save "" --appendonly no >/dev/null

docker run --detach --name "$REDPANDA_CONTAINER" --network "$E2E_NETWORK" \
    --publish "127.0.0.1:$KAFKA_PORT:19092" \
    "$REDPANDA_IMAGE" redpanda start \
    --overprovisioned --smp 1 --memory 512M --reserve-memory 0M --check=false \
    --node-id 0 \
    --kafka-addr "internal://0.0.0.0:9092,external://0.0.0.0:19092" \
    --advertise-kafka-addr \
    "internal://$REDPANDA_CONTAINER:9092,external://127.0.0.1:$KAFKA_PORT" >/dev/null

e2e_wait_for_command postgres 90 docker exec "$POSTGRES_CONTAINER" \
    pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"
e2e_wait_for_command redis 60 docker exec "$REDIS_CONTAINER" redis-cli ping
e2e_wait_for_command redpanda 90 docker exec "$REDPANDA_CONTAINER" \
    rpk cluster health --exit-when-healthy

NGINX_CONFIG="$E2E_STATE_DIR/nginx.conf"
e2e_render_nginx_config \
    "$SCRIPT_DIR/nginx.conf.template" "$NGINX_CONFIG" \
    80 \
    host.docker.internal "$BACKEND_PORT" host.docker.internal "$FRONTEND_PORT"
e2e_write_state_value E2E_NGINX_CONFIG "$NGINX_CONFIG"

docker run --rm --add-host host.docker.internal:host-gateway \
    --volume "$NGINX_CONFIG:/etc/nginx/nginx.conf:ro" \
    "$NGINX_IMAGE" nginx -t >/dev/null

docker run --detach --name "$NGINX_CONTAINER" --network "$E2E_NETWORK" \
    --add-host host.docker.internal:host-gateway \
    --publish "127.0.0.1:$NGINX_PORT:80" \
    --volume "$NGINX_CONFIG:/etc/nginx/nginx.conf:ro" \
    "$NGINX_IMAGE" >/dev/null

trap - EXIT
printf 'E2E runtime provisioned: %s\n' "$E2E_STATE_FILE"
