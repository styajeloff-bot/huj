#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../../.."
name="carcraft-22296-cleanup-regression-$$"
network="$name-net"
cleanup() {
  docker rm -f "$name-runner" "$name-pg" >/dev/null 2>&1 || true
  docker network rm "$network" >/dev/null 2>&1 || true
}
trap cleanup EXIT
docker network create --internal "$network" >/dev/null
docker run -d --name "$name-pg" --network "$network" --network-alias cleanup-pg \
  --memory 256m --cpus 1 --pids-limit 100 --tmpfs /var/lib/postgresql/data:rw,size=128m \
  -e POSTGRES_USER=cleanup_regression -e POSTGRES_DB=cleanup_regression -e POSTGRES_HOST_AUTH_METHOD=trust \
  postgres:15-alpine -c max_connections=10 -c max_locks_per_transaction=10 -c shared_buffers=16MB >/dev/null
for attempt in $(seq 1 60); do
  if docker exec "$name-pg" pg_isready -U cleanup_regression -d cleanup_regression >/dev/null 2>&1; then break; fi
  sleep 1
done
docker exec "$name-pg" pg_isready -U cleanup_regression -d cleanup_regression >/dev/null
docker run --rm --name "$name-runner" --network "$network" --memory 384m --cpus 1 --pids-limit 100 \
  --mount "type=bind,source=$PWD/backend,target=/source,readonly" \
  --mount "type=bind,source=$PWD/scripts/e2e/22296,target=/e2e,readonly" \
  -e PYTHONPATH=/source -e DB_HOST=cleanup-pg -e DB_NAME=cleanup_regression \
  -e DB_USER=cleanup_regression -e DB_PASSWORD=local-only -e DADATA_API_KEY= -e SMTP_HOST= -e SMSC_LOGIN= \
  --entrypoint /app/.venv/bin/python carcraft-documentregistry22296-backend:local /e2e/cleanup_locks.py
