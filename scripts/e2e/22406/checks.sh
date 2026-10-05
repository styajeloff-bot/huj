#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../../.."
docker run --rm --user 0:0 -e UV_CACHE_DIR=/tmp/uv-cache \
  --mount "type=bind,source=$PWD/backend,target=/source" \
  -w /source -e UV_PROJECT_ENVIRONMENT=/app/.venv -e PYTHONPATH=/source \
  --entrypoint sh carcraft-22406-backend:local -c '
    uv pip install --python /app/.venv/bin/python pytest pytest-asyncio fakeredis types-defusedxml types-requests &&
    uv run --no-sync ruff check . --fix &&
    uv run --no-sync lint-imports &&
    uv run --no-sync mypy .
  '
