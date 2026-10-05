#!/usr/bin/env bash
set -euo pipefail
TASK_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TASK_ROOT="$(cd "$TASK_SCRIPT_DIR/../../.." && pwd)"
TASK_ARTIFACTS="${E2E_22398_ARTIFACT_DIR:-$TASK_ROOT/artifacts/e2e/22398}"
TASK_COMPOSE=(docker compose -f "$TASK_SCRIPT_DIR/compose.yml")
mkdir -p "$TASK_ARTIFACTS"
TASK_KEEP=false
if [[ "${1:-}" == --keep ]]; then TASK_KEEP=true; shift; fi
if (($#)); then echo 'Usage: run.sh [--keep]' >&2; exit 2; fi
finish() {
  local result=$?
  trap - EXIT
  "${TASK_COMPOSE[@]}" logs --no-color > "$TASK_ARTIFACTS/docker.log" 2>&1 || true
  if [[ "$TASK_KEEP" == false ]]; then "${TASK_COMPOSE[@]}" down -v >/dev/null 2>&1 || true; fi
  exit "$result"
}
trap finish EXIT
"${TASK_COMPOSE[@]}" build backend frontend nginx
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
"${TASK_COMPOSE[@]}" run --rm backend /app/.venv/bin/alembic upgrade head
"${TASK_COMPOSE[@]}" run --rm backend /app/.venv/bin/alembic check | tee "$TASK_ARTIFACTS/alembic.log"
"${TASK_COMPOSE[@]}" run --rm backend /app/.venv/bin/python /e2e/prepare.py
"${TASK_COMPOSE[@]}" up -d backend frontend
"${TASK_COMPOSE[@]}" up -d --force-recreate nginx
TASK_BACKEND_ID="$("${TASK_COMPOSE[@]}" ps -q backend)"
docker cp "$TASK_BACKEND_ID:/runtime/artifacts/." "$TASK_ARTIFACTS/"
cd "$TASK_ROOT/frontend"
E2E_BASE_URL="${E2E_BASE_URL:-http://localhost:18398}" E2E_22398_ARTIFACT_DIR="$TASK_ARTIFACTS" \
  bun run test:e2e -- tests/e2e/workspace/22398-employee-list.spec.ts --workers=1
