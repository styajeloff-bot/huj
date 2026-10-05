"""Redis-backed throttle for admin Mobile ID diagnostic requests."""
from __future__ import annotations

import logging
from typing import Any, Protocol, cast
from uuid import UUID

from redis.exceptions import RedisError

from infrastructure.cache.redis_client import get_redis
from infrastructure.settings import settings

logger = logging.getLogger("carcraft-backend")

_KEY_PREFIX = "mobile-id:diagnostics:"


class MobileIdDiagnosticsRateLimitExceededError(RuntimeError):
    pass


class MobileIdDiagnosticsRateLimitUnavailableError(RuntimeError):
    pass


class _RateLimitRedis(Protocol):
    async def incr(self, key: str) -> Any: ...

    async def expire(self, key: str, seconds: int) -> Any: ...


def _key(actor_id: UUID) -> str:
    return f"{_KEY_PREFIX}{actor_id}"


async def enforce_mobile_id_diagnostics_rate_limit(actor_id: UUID) -> None:
    limit = settings.mobile_id_diagnostics_rate_limit_per_window
    window_seconds = settings.mobile_id_diagnostics_rate_limit_window_seconds
    if limit <= 0 or window_seconds <= 0:
        return
    try:
        client = cast("_RateLimitRedis", get_redis())
        count = int(await client.incr(_key(actor_id)))
        await client.expire(_key(actor_id), window_seconds)
    except (RedisError, RuntimeError) as exc:
        logger.warning(
            "mobile_id_diagnostics_rate_limit_failed actor_id=%s err=%s",
            actor_id,
            exc,
        )
        raise MobileIdDiagnosticsRateLimitUnavailableError from exc
    if count > limit:
        raise MobileIdDiagnosticsRateLimitExceededError
