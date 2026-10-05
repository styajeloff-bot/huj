"""Isolated production Taskiq expiry E2E; launched only by taskiq_run.py."""
# ruff: noqa: E402
# Bootstrap must validate fixture resources before production imports.

import taskiq_bootstrap  # noqa: F401 - validates and isolates transport before app import
from runtime import guard

guard()
from infrastructure.crypto.key_configuration import load_and_validate_key_configuration

load_and_validate_key_configuration()
from infrastructure.cache.redis_client import startup_redis
from main import app


@app.middleware("http")
async def initialize_auth(request, call_next):
    await startup_redis()
    return await call_next(request)
