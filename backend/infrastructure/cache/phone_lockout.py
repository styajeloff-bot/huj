"""Redis-backed lockout for failed OTP verification attempts.

Counts failures per phone; when the count exceeds
``settings.otp_max_failures`` within ``settings.otp_lockout_window_seconds``,
further attempts are rejected for the remainder of the window.

Fail behavior:
  - If Redis is reachable → authoritative answer.
  - If Redis is down → fail-open on the READ path (``is_locked`` returns
    False). Locking is a secondary defence; primary is rate-limiting at
    the edge. Better than 500-ing every verify call if Redis blips.
"""
from __future__ import annotations

import logging
from typing import Any, Protocol, cast

from redis.exceptions import RedisError

from infrastructure.cache.redis_client import get_redis
from infrastructure.settings import settings

logger = logging.getLogger("carcraft-backend")

_KEY_PREFIX = "auth:otp_failures:"


class _LockoutRedis(Protocol):
    async def incr(self, key: str) -> Any: ...

    async def expire(self, key: str, seconds: int) -> Any: ...


def _key(phone: str) -> str:
    return f"{_KEY_PREFIX}{phone}"


async def is_locked(phone: str) -> bool:
    """True if the phone has exceeded the failure threshold within the window."""
    try:
        value = await get_redis().get(_key(phone))
    except RedisError as exc:
        logger.warning("otp_lockout_read_failed phone=%s err=%s", phone, exc)
        return False
    if value is None:
        return False
    try:
        count = int(value if isinstance(value, int | str) else value.decode())
    except (TypeError, ValueError):
        return False
    return count >= settings.otp_max_failures


async def register_failure(phone: str) -> int:
    """Increment the failure counter for ``phone``. Returns the new count."""
    try:
        client = cast("_LockoutRedis", get_redis())
        # INCR creates the key at 1; EXPIRE (re)arms the window on every
        # failure so consecutive wrong codes keep the lock active.
        new_count = await _incr(client, _key(phone))
        await _expire(client, _key(phone), settings.otp_lockout_window_seconds)
        return new_count
    except RedisError as exc:
        logger.warning("otp_lockout_write_failed phone=%s err=%s", phone, exc)
        return 0


async def clear(phone: str) -> None:
    """Reset the failure counter after a successful verification."""
    try:
        await get_redis().delete(_key(phone))
    except RedisError as exc:
        logger.warning("otp_lockout_clear_failed phone=%s err=%s", phone, exc)


async def _incr(client: _LockoutRedis, key: str) -> int:
    """redis-py's INCR. Extracted so the Protocol can stay minimal."""
    return int(await client.incr(key))


async def _expire(client: _LockoutRedis, key: str, seconds: int) -> None:
    await client.expire(key, seconds)
