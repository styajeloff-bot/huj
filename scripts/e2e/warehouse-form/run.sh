#!/usr/bin/env bash
set -euo pipefail
TASK_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TASK_ROOT="$(cd "$TASK_SCRIPT_DIR/../../.." && pwd)"
TASK_ARTIFACTS="${E2E_WAREHOUSE_FORM_ARTIFACT_DIR:-$TASK_ROOT/artifacts/e2e/warehouse-form}"
TASK_COMPOSE=(docker compose -f "$TASK_SCRIPT_DIR/compose.yml")
mkdir -p "$TASK_ARTIFACTS"
TASK_KEEP=false
TASK_TUNNEL_PID=""
if [[ "${1:-}" == --keep ]]; then TASK_KEEP=true; shift; fi
if (($#)); then echo 'Usage: run.sh [--keep]' >&2; exit 2; fi
finish() {
  local result=$?
  trap - EXIT
  "${TASK_COMPOSE[@]}" logs --no-color > "$TASK_ARTIFACTS/docker.log" 2>&1 || true
  if [[ -n "$TASK_TUNNEL_PID" ]]; then kill "$TASK_TUNNEL_PID" 2>/dev/null || true; fi
  if [[ "$TASK_KEEP" == false ]]; then "${TASK_COMPOSE[@]}" down -v >/dev/null 2>&1 || true; fi
  exit "$result"
}
trap finish EXIT
"${TASK_COMPOSE[@]}" build --ssh "default=${E2E_SDK_SSH_KEY:-$TASK_ROOT/backend/id_ed25519}" backend frontend nginx
"${TASK_COMPOSE[@]}" up -d postgres redis redpanda
"${TASK_COMPOSE[@]}" run --rm backend /app/.venv/bin/python -c '
from pathlib import Path
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization
p = Path("/runtime/jwt")
p.mkdir(parents=True, exist_ok=True)
k = ec.generate_private_key(ec.SECP256R1())
(p / "e2e.pem").write_bytes(k.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
(p / "e2e.pub.pem").write_bytes(k.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
'
"${TASK_COMPOSE[@]}" run --rm -w /source backend /app/.venv/bin/alembic upgrade 164
"${TASK_COMPOSE[@]}" run -T --rm backend /app/.venv/bin/python - --legacy < "$TASK_SCRIPT_DIR/prepare.py"
"${TASK_COMPOSE[@]}" run --rm -w /source backend /app/.venv/bin/alembic upgrade head
"${TASK_COMPOSE[@]}" run --rm -w /source backend /app/.venv/bin/alembic check | tee "$TASK_ARTIFACTS/alembic.log"
"${TASK_COMPOSE[@]}" run -T --rm backend /app/.venv/bin/python - < "$TASK_SCRIPT_DIR/prepare.py"
"${TASK_COMPOSE[@]}" up -d --force-recreate backend frontend
"${TASK_COMPOSE[@]}" up -d --force-recreate nginx
TASK_BACKEND_ID="$("${TASK_COMPOSE[@]}" ps -q backend)"
docker cp "$TASK_BACKEND_ID:/runtime/artifacts/." "$TASK_ARTIFACTS/"
# Docker may run on an SSH context. Forward only this isolated stand's port.
if ! curl -fsS http://localhost:18418/api/v1/health >/dev/null 2>&1; then
  TASK_DOCKER_ENDPOINT="$(docker context inspect --format '{{.Endpoints.docker.Host}}')"
  if [[ "$TASK_DOCKER_ENDPOINT" == ssh://* ]]; then
    ssh -N -L 18418:127.0.0.1:18418 "${TASK_DOCKER_ENDPOINT#ssh://}" &
    TASK_TUNNEL_PID=$!
  fi
fi
for attempt in {1..30}; do
  if curl -fsS http://localhost:18418/api/v1/health >/dev/null 2>&1; then break; fi
  sleep 1
done
cd "$TASK_ROOT/frontend"
E2E_BASE_URL="${E2E_BASE_URL:-http://localhost:18418}" E2E_WAREHOUSE_FORM_ARTIFACT_DIR="$TASK_ARTIFACTS" \
  bun run test:e2e -- tests/e2e/workspace/warehouse-form.spec.ts --workers=1
