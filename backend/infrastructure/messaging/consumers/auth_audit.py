"""FastStream consumer that persists auth events to ClickHouse.

Subscribes to ``auth.events.v1`` via the shared broker singleton. Every
message produced by ``infrastructure/messaging/auth_events.py`` lands
here and is inserted into the ``auth_audit_log`` ClickHouse table.

Failures are logged and swallowed — a broken ClickHouse connection or
malformed event drops the record rather than stalling the consumer group.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from infrastructure.clickhouse import execute_clickhouse
from infrastructure.logging import log_event
from infrastructure.messaging.broker import broker
from infrastructure.messaging.topics import AUTH_EVENTS
from infrastructure.settings import settings

# Known envelope keys that are promoted to columns. Everything else in
# the published dict goes into ``payload`` as JSON. Keeping this list
# small on purpose.
_COLUMN_KEYS: frozenset[str] = frozenset({"event", "timestamp", "user_id", "phone"})


def _parse_timestamp(raw: Any) -> datetime:
    """Parse an ISO-8601 string (or pre-built datetime) into UTC-aware dt."""
    if isinstance(raw, datetime):
        return raw if raw.tzinfo is not None else raw.replace(tzinfo=UTC)
    if isinstance(raw, str):
        parsed = datetime.fromisoformat(raw)
        return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)
    return datetime.now(UTC)


def _parse_user_id(raw: Any) -> UUID | None:
    if isinstance(raw, UUID):
        return raw
    if not isinstance(raw, str):
        return None
    try:
        return UUID(raw)
    except ValueError:
        return None


def _coerce_phone(raw: Any) -> str | None:
    if raw is None:
        return None
    phone = str(raw)
    return phone[:32] if phone else None


def _to_json(payload: dict[str, Any]) -> str:
    import json
    return json.dumps(payload, default=str, ensure_ascii=False)


async def handle_auth_event(message: dict[str, Any]) -> None:
    """Persist a single auth event envelope to ClickHouse ``auth_audit_log``.

    Exposed as a module-level function so tests can feed dict payloads
directly without spinning up Kafka.
    """
    if not isinstance(message, dict):
        log_event(
            "warning",
            "auth_audit.payload_invalid",
            "Authentication audit event has an invalid envelope",
            component="auth_audit",
            payload_type=type(message).__name__,
        )
        return

    event = message.get("event")
    if not event or not isinstance(event, str):
        log_event(
            "warning",
            "auth_audit.event_missing",
            "Authentication audit event has no event name",
            component="auth_audit",
            field_count=len(message),
        )
        return

    event_name = event[:64]
    timestamp = _parse_timestamp(message.get("timestamp"))
    user_id = _parse_user_id(message.get("user_id"))
    phone = _coerce_phone(message.get("phone"))
    payload = {k: v for k, v in message.items() if k not in _COLUMN_KEYS} or None

    try:
        await execute_clickhouse(
            """
            INSERT INTO auth_audit_log (event, timestamp, user_id, phone, payload)
            VALUES (%(event)s, %(timestamp)s, %(user_id)s, %(phone)s, %(payload)s)
            """,
            params={
                "event": event_name,
                "timestamp": timestamp.isoformat(),
                "user_id": user_id,
                "phone": phone,
                "payload": _to_json(payload) if payload else "{}",
            },
        )
    except Exception as exc:
        log_event(
            "error",
            "auth_audit.persist_failed",
            "Authentication audit event could not be persisted",
            error=exc,
            component="auth_audit",
            operation="insert",
            audit_event=event_name,
        )


@broker.subscriber(AUTH_EVENTS, group_id=settings.kafka_auth_audit_consumer_group)
async def consume_auth_event(message: dict[str, Any]) -> None:
    """Kafka subscriber — delegates to :func:`handle_auth_event`."""
    await handle_auth_event(message)
