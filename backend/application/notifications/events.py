"""Small producer seam: append a fact in the caller's business transaction."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from domain.events.notifications import NotificationEvent
from infrastructure.logging import get_log_context_field
from infrastructure.repositories import notification_outbox_repository as repo


def normalize_notification_value(value: Any) -> Any:
    """Canonical, idempotent value projection for snapshots and event payloads."""
    if isinstance(value, UUID | Decimal):
        return str(value)
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Notification timestamps must be timezone aware")
        return value.isoformat()
    if isinstance(value, date):
        raise TypeError("Notification timestamps cannot be date-only")
    if isinstance(value, dict):
        return {key: normalize_notification_value(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [normalize_notification_value(item) for item in value]
    return value


async def record_notification_event(
    session: AsyncSession,
    *,
    event_type: str,
    entity_type: str,
    entity_id: UUID,
    aggregate_id: UUID,
    request_number: str,
    actor_user_id: UUID | None = None,
    application_id: UUID | None = None,
    previous_values: dict | None = None,
    new_values: dict | None = None,
    payload: dict | None = None,
    occurrence_key: str | None = None,
    occurred_at: datetime | None = None,
) -> UUID | None:
    """No commit, network or scheduling: rollback also removes the event."""
    previous = normalize_notification_value(previous_values or {})
    new = normalize_notification_value(new_values or {})
    changed = sorted(
        key for key in previous.keys() | new.keys() if previous.get(key) != new.get(key)
    )
    event = NotificationEvent.model_validate(
        {
            "event_id": uuid4(),
            "event_type": event_type,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "aggregate_id": aggregate_id,
            "application_id": application_id,
            "actor_user_id": actor_user_id,
            "request_number": request_number,
            "occurred_at": occurred_at or datetime.now(UTC),
            "changed_fields": changed,
            "previous_values": {key: previous.get(key) for key in changed},
            "new_values": {key: new.get(key) for key in changed},
            "payload": normalize_notification_value(payload or {}),
            "occurrence_key": occurrence_key,
            "correlation_id": get_log_context_field("correlation_id"),
        }
    )
    event_id = await repo.append_event(session, event)
    if event_id:
        session.info["notification_outbox_pending"] = True
    return event_id
