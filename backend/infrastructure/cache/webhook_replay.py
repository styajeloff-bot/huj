"""Redis-backed replay protection for payment webhooks.

A signed webhook proves the message was issued by the gateway at *some*
point — it does not prove freshness. An attacker who captured a valid
``payment.succeeded`` callback can re-send it and, without replay
protection, mark the same order paid twice. We stash a nonce per webhook
(typically ``transaction_id + ":" + signature``) in Redis with a TTL
covering the plausible replay window, and atomic-check it on every
arrival via ``SET … NX``.

Fail behavior:
  - If Redis is reachable → authoritative answer (atomic set-if-missing).
  - If Redis is down → defaults to ``fail closed`` (treat as replay,
    drop the webhook) unless ``settings.webhook_replay_fail_open`` is
    set. Rationale: a silent bypass of replay protection re-opens the
    exact attack we're defending against; a temporary webhook drop is
    recoverable (the gateway won't retry because we still return 200,
    but ops can reconcile via the status polling endpoint).
"""
from __future__ import annotations

import logging

from redis.exceptions import RedisError

from infrastructure.cache.redis_client import get_redis
from infrastructure.settings import settings

logger = logging.getLogger("carcraft-backend")

_KEY_PREFIX = "webhook:nonce:"


def _key(nonce: str) -> str:
    return f"{_KEY_PREFIX}{nonce}"


async def seen_before(nonce: str) -> bool:
    """Atomically record ``nonce`` or report that it was already seen.

    Uses ``SET key 1 EX ttl NX`` so the check-and-insert is a single
    round-trip — no TOCTOU window between a separate EXISTS + SET.

    Returns:
        True  — the nonce was already present (treat as replay).
        False — first sight, caller may proceed with processing.

    On Redis error we honour ``settings.webhook_replay_fail_open``:
    default is False → return True (fail closed, drop the webhook).
    """
    if not nonce:
        # An empty nonce would collide across unrelated webhooks — treat
        # as replay so we never accidentally blanket-allow.
        return True
    ttl = settings.webhook_replay_window_seconds
    try:
        result = await get_redis().set(_key(nonce), b"1", ex=ttl, nx=True)
    except RedisError as exc:
        logger.error("webhook_replay_lookup_failed nonce_prefix=%s err=%s", nonce[:16], exc)
        return not settings.webhook_replay_fail_open
    # redis-py returns True when SET actually wrote (first sight) and
    # None when NX blocked the write (already existed = replay).
    return result is None
