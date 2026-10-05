#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE=(docker compose -p carcraft-22320-e2e -f "$SCRIPT_DIR/compose.yml")
"${COMPOSE[@]}" build backend frontend
"${COMPOSE[@]}" up -d postgres redis redpanda minio init-keys
"${COMPOSE[@]}" run --rm -T backend /app/.venv/bin/python /e2e/runtime.py migrate
"${COMPOSE[@]}" up -d --wait backend
"${COMPOSE[@]}" exec -T backend /app/.venv/bin/python /e2e/runtime.py seed
"${COMPOSE[@]}" exec -T backend /app/.venv/bin/python /e2e/runtime.py verify
"${COMPOSE[@]}" exec -T backend /app/.venv/bin/python /e2e/runtime.py check
"${COMPOSE[@]}" up -d frontend nginx
"${COMPOSE[@]}" exec -T backend /app/.venv/bin/python - <<'PY'
import time
import httpx
for attempt in range(60):
    try:
        response = httpx.get("http://nginx/", timeout=2, trust_env=False)
        if response.status_code == 200:
            print("Frontend and nginx ready", flush=True)
            break
    except httpx.HTTPError:
        pass
    time.sleep(1)
else:
    raise RuntimeError("Frontend/nginx did not become ready")
PY
bash "$SCRIPT_DIR/browser.sh"
"${COMPOSE[@]}" logs --no-color --since=15m backend frontend nginx | "${COMPOSE[@]}" exec -T backend sh -c 'cat > /runtime/services.log'
