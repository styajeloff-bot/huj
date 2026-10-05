"""JWT access-token denylist backed by Redis.

A token's ``jti`` is placed on the denylist with a TTL equal to the token's
remaining lifetime — no point outliving ``exp``. On every authenticated
request we check the denylist before trusting the token.

Fail behavior:
  - If Redis is reachable → authoritative answer.
  - If Redis is down → defaults to ``fail closed`` (treat as revoked) unless
    ``settings.auth_denylist_fail_open`` is set. Rationale: a silent bypass
    of revocation is worse than a temporary 5xx.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime

from redis.exceptions import RedisError

from infrastructure.cache.redis_client import get_redis
from infrastructure.settings import settings

logger = logging.getLogger("carcraft-backend")

_KEY_PREFIX = "auth:denylist:jti:"


def _key(jti: str) -> str:
    return f"{_KEY_PREFIX}{jti}"


def _ttl_from_exp(exp: int | float | None) -> int:
    """Seconds remaining until ``exp`` (JWT standard claim, Unix epoch)."""
    if exp is None:
        return settings.access_token_expiry_minutes * 60
    now = datetime.now(UTC).timestamp()
    remaining = int(float(exp) - now)
    return max(remaining, 1)


async def revoke(jti: str, *, exp: int | float | None) -> None:
    """Put ``jti`` on the denylist with a TTL matching the token's exp."""
    if not jti:
        return
    ttl = _ttl_from_exp(exp)
    try:
        await get_redis().set(_key(jti), b"1", ex=ttl)
    except RedisError as exc:
        logger.error("Denylist revoke failed for jti=%s: %s", jti, exc)
        # Surface as AuthDenylistError so the router can return 500 rather
        # than pretending logout succeeded.
        raise AuthDenylistError("Не удалось отозвать токен") from exc


async def is_revoked(jti: str | None) -> bool:
    """Check whether a JWT's ``jti`` has been revoked."""
    if not jti:
        return False
    try:
        exists = await get_redis().exists(_key(jti))
    except RedisError as exc:
        logger.error("Denylist lookup failed for jti=%s: %s", jti, exc)
        return not settings.auth_denylist_fail_open
    return exists > 0


class AuthDenylistError(RuntimeError):
    """Raised when a denylist write fails — caller must propagate to 5xx."""
