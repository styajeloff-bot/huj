"""FastStream consumer that dispatches email + SMS alerts on security-sensitive auth events.

Subscribes to ``auth.events.v1`` (same topic as the audit consumer) under
a **separate** consumer group so both consumers see every event. The
handler filters for a short list of user-facing events and sends email +
SMS via the adapters in :mod:`infrastructure.services.security_notifications`.

Throttling (Redis ``SET NX`` per ``user_id`` + fingerprint) prevents
spam when the same event repeats within a short window — e.g. 20 logins
from the same IP must not generate 20 emails.

Failure policy: never re-raise. A broken SMTP connection or malformed
event is logged at ``WARNING`` and dropped. The audit consumer will
still persist the same event independently.
"""
from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from redis.exceptions import RedisError

from infrastructure.cache.redis_client import get_redis
from infrastructure.database import AsyncSessionLocal
from infrastructure.messaging.auth_events import (
    LOGIN_SUCCEEDED,
    MFA_DISABLED,
    REFRESH_REUSE_DETECTED,
    SESSIONS_REVOKED_ALL,
)
from infrastructure.messaging.broker import broker
from infrastructure.messaging.topics import AUTH_EVENTS
from infrastructure.models.users import User, UserSession
from infrastructure.services.security_notifications import (
    send_mfa_disabled_notification,
    send_new_device_notification,
    send_refresh_reuse_notification,
    send_sessions_revoked_all_notification,
)
from infrastructure.settings import settings

logger = logging.getLogger("carcraft-backend")

def _coerce_int(raw: Any) -> int | None:
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _coerce_uuid(raw: Any) -> UUID | None:
    if raw is None:
        return None
    if isinstance(raw, UUID):
        return raw
    try:
        return UUID(str(raw))
    except (TypeError, ValueError):
        return None


def _fingerprint(*parts: str | None) -> str:
    """SHA-256 hex digest of the (ip, ua) tuple — stable, bounded length."""
    joined = "|".join(part or "" for part in parts)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:32]


async def _should_send(event: str, user_id: UUID, fingerprint: str) -> bool:
    """Claim a throttle slot in Redis via ``SET NX``.

    Returns True if the slot was acquired (caller should dispatch);
    False if another invocation already claimed it within the TTL, or if
    Redis itself is unreachable. Fail-closed on Redis errors: better to
    drop an alert than to spam the user when Redis flaps.
    """
    key = f"notify:{event}:{user_id}:{fingerprint}"
    ttl = settings.security_notification_throttle_seconds
    try:
        claimed = await get_redis().set(key, "1", ex=ttl, nx=True)
    except RedisError as exc:
        logger.warning(
            "security_notify_throttle_redis_failed event=%s user_id=%s err=%s",
            event,
            user_id,
            exc,
        )
        return False
    return bool(claimed)


async def _load_user(user_id: UUID) -> dict[str, Any] | None:
    """Read-only user fetch — returns the minimal dict the notifiers need.

    Deliberately avoids ``infrastructure.repositories.auth_repository`` so
    it doesn't become an accidental dependency surface for this consumer
    (spec forbids modifying that module). The query is a single row by
    primary key; generic SQLAlchemy Core is fine.
    """
    async with AsyncSessionLocal() as session:
        row = (
            await session.execute(
                sa.select(User.id, User.phone, User.email, User.name).where(
                    User.id == user_id
                )
            )
        ).first()
    if row is None:
        return None
    return {
        "id": row[0],
        "phone": row[1],
        "email": row[2],
        "name": row[3],
    }


async def _is_new_device(
    user_id: UUID,
    ip_address: str | None,
    exclude_session_id: UUID | None,
) -> bool:
    """True iff no session in the lookback window shares this IP.

    A single SELECT EXISTS against ``user_sessions`` — cheap and ordered
    by the existing ``idx_user_sessions_user_id_last_used_at_desc`` index.
    When ``ip_address`` is missing we can't meaningfully compare, so we
    treat it as "not new" to avoid noisy alerts on bad producers.
    """
    if not ip_address:
        return False
    cutoff = datetime.now(UTC) - timedelta(
        days=settings.security_new_device_lookback_days
    )
    async with AsyncSessionLocal() as session:
        stmt = sa.select(
            sa.exists(
                sa.select(UserSession.id).where(
                    UserSession.user_id == user_id,
                    UserSession.ip_address == ip_address,
                    UserSession.created_at >= cutoff,
                    *(
                        [UserSession.id != exclude_session_id]
                        if exclude_session_id is not None
                        else []
                    ),
                )
            )
        )
        result = await session.execute(stmt)
    return not bool(result.scalar())


# ---------------------------------------------------------------------------
# Event handlers
# ---------------------------------------------------------------------------


async def _handle_login_succeeded(message: dict[str, Any]) -> None:
    user_id = _coerce_uuid(message.get("user_id"))
    if user_id is None:
        return

    ip_address = message.get("ip") or message.get("ip_address")
    user_agent = message.get("user_agent") or message.get("ua")
    session_id = _coerce_uuid(message.get("session_id"))

    if not await _is_new_device(user_id, ip_address, session_id):
        return

    fingerprint = _fingerprint(ip_address, user_agent)
    if not await _should_send("new_device", user_id, fingerprint):
        return

    user = await _load_user(user_id)
    if user is None:
        return

    await send_new_device_notification(
        user,
        {
            "ip_address": ip_address,
            "user_agent": user_agent,
            "session_id": session_id,
        },
    )


async def _handle_mfa_disabled(message: dict[str, Any]) -> None:
    user_id = _coerce_uuid(message.get("user_id"))
    if user_id is None:
        return
    if not await _should_send("mfa_disabled", user_id, "const"):
        return
    user = await _load_user(user_id)
    if user is None:
        return
    await send_mfa_disabled_notification(user)


async def _handle_sessions_revoked_all(message: dict[str, Any]) -> None:
    user_id = _coerce_uuid(message.get("user_id"))
    if user_id is None:
        return
    if not await _should_send("sessions_revoked_all", user_id, "const"):
        return
    user = await _load_user(user_id)
    if user is None:
        return
    await send_sessions_revoked_all_notification(user)


async def _handle_refresh_reuse(message: dict[str, Any]) -> None:
    user_id = _coerce_uuid(message.get("user_id"))
    if user_id is None:
        return
    if not await _should_send("refresh_reuse", user_id, "const"):
        return
    user = await _load_user(user_id)
    if user is None:
        return
    sessions_killed = _coerce_int(message.get("sessions_killed")) or 0
    await send_refresh_reuse_notification(user, sessions_killed)


_DISPATCH = {
    LOGIN_SUCCEEDED: _handle_login_succeeded,
    MFA_DISABLED: _handle_mfa_disabled,
    SESSIONS_REVOKED_ALL: _handle_sessions_revoked_all,
    REFRESH_REUSE_DETECTED: _handle_refresh_reuse,
}


async def handle_security_notification(event: dict[str, Any]) -> None:
    """Drive the dispatch table from a plain dict.

    Exposed as a module-level function so tests can feed payloads
    directly without a running Kafka broker — same idea as
    :func:`infrastructure.messaging.consumers.auth_audit.handle_auth_event`.
    """
    if not settings.security_notifications_enabled:
        return
    if not isinstance(event, dict):
        logger.warning(
            "security_notify_bad_payload type=%s", type(event).__name__
        )
        return

    event_name = event.get("event")
    if not isinstance(event_name, str) or not event_name:
        return

    handler = _DISPATCH.get(event_name)
    if handler is None:
        return  # Silently ignore events we don't react to.

    try:
        await handler(event)
    except Exception as exc:
        # Swallow — notifications are observational; a stalled consumer
        # is worse than a missed email.
        logger.warning(
            "security_notify_handler_failed event=%s err=%s", event_name, exc
        )


@broker.subscriber(AUTH_EVENTS, group_id=settings.kafka_auth_notifications_consumer_group)
async def consume_security_notification(message: dict[str, Any]) -> None:
    """Kafka subscriber — delegates to :func:`handle_security_notification`."""
    await handle_security_notification(message)
