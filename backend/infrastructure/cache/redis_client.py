"""Async Redis client lifecycle.

Single process-wide `redis.asyncio.Redis` instance, started/stopped from the
FastAPI lifespan. Tests can inject a fake via `set_redis(...)`.
"""
from __future__ import annotations

import logging
from typing import Protocol, cast, runtime_checkable

from redis.asyncio import from_url

from infrastructure.settings import settings

logger = logging.getLogger("carcraft-backend")


@runtime_checkable
class RedisLike(Protocol):
    """Narrow surface used by the app — implemented by redis.asyncio.Redis and fakeredis."""

    async def set(
        self,
        name: str,
        value: str | bytes | int | float,
        *,
        ex: int | None = ...,
        px: int | None = ...,
        nx: bool = ...,
        xx: bool = ...,
    ) -> bool | None: ...

    async def get(self, name: str) -> bytes | None: ...

    async def delete(self, *names: str) -> int: ...

    async def exists(self, *names: str) -> int: ...

    async def ping(self) -> bool: ...

    async def aclose(self) -> None: ...


class _ClientState:
    client: RedisLike | None = None


def set_redis(client: RedisLike | None) -> None:
    """Replace the global client (tests / lifespan)."""
    _ClientState.client = client


def get_redis() -> RedisLike:
    """Return the initialized client or raise — never returns None."""
    if _ClientState.client is None:
        raise RuntimeError(
            "Redis client is not initialized — startup_redis() must run first."
        )
    return _ClientState.client


async def startup_redis() -> None:
    """Connect to Redis and verify with PING. Called from FastAPI lifespan."""
    if _ClientState.client is not None:
        return
    client = cast(
        "RedisLike",
        from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=False,
            socket_connect_timeout=settings.redis_connect_timeout_seconds,
        ),
    )
    await client.ping()
    _ClientState.client = client
    logger.info("Redis connected: %s", _sanitize(settings.redis_url))


async def shutdown_redis() -> None:
    """Close the Redis connection pool. Called from FastAPI lifespan."""
    if _ClientState.client is None:
        return
    try:
        await _ClientState.client.aclose()
    except Exception as exc:
        logger.warning("Redis shutdown error: %s", exc)
    finally:
        _ClientState.client = None


def _sanitize(url: str) -> str:
    """Strip credentials from a redis:// URL for log output."""
    if "@" not in url:
        return url
    scheme, _, tail = url.partition("://")
    _, _, host = tail.rpartition("@")
    return f"{scheme}://***@{host}"
