"""One expiry rule for writes, recovery scans, and worker revalidation."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.notifications.events import record_notification_event
from domain.events.notifications import NotificationEvent
from domain.reference_document_expiry import (
    business_date,
    expiry_is_due,
    expiry_occurrence_key,
)
from infrastructure.repositories import (
    notification_document_registry_repository as repo,
)


async def record_document_expiry_if_due(
    session: AsyncSession,
    document_id: UUID,
    *,
    actor_user_id: UUID | None = None,
    now: datetime | None = None,
    on_activation: bool = False,
) -> UUID | None:
    """Record after the write's flush, before its commit; never publish here."""
    now = now or datetime.now(UTC)
    record = await repo.get_document_context(session, document_id)
    if (record is None or record["deactivated_at"] is not None
        or not expiry_is_due(record["valid_to"], now)):
        return None
    valid_to = record["valid_to"]
    occurrence_key = expiry_occurrence_key(document_id, record["version_id"], valid_to)
    event_id = await record_notification_event(
        session, event_type="document_registry.expiring", entity_type="reference_document",
        entity_id=document_id, aggregate_id=document_id,
        request_number=record["contract_number"], actor_user_id=actor_user_id,
        occurred_at=now,
        payload={
            "version_id": record["version_id"], "valid_to": valid_to.isoformat(),
            "document_type": record["document_type"], "document_name": record["name"],
        },
        occurrence_key=occurrence_key,
    )
    if event_id is None and on_activation:
        event_id = await repo.rearm_undelivered_expiry(session, occurrence_key, now)
        if event_id is not None:
            session.info["notification_outbox_pending"] = True
    return event_id


async def scan_document_registry_expiries(session: AsyncSession, now: datetime) -> int:
    """Catch up any still-current version inside the 30-day calendar window."""
    today = business_date(now)
    count = 0
    after_id = None
    while document_ids := await repo.list_due_document_ids(session, today, after_id=after_id):
        for document_id in document_ids:
            count += bool(await record_document_expiry_if_due(session, document_id, now=now))
        after_id = document_ids[-1]
    return count


async def document_expiry_is_current(
    session: AsyncSession, event: NotificationEvent, now: datetime,
) -> bool:
    """Hold a document read lock until the inbox fan-out commits."""
    record = await repo.get_document_context(session, event.entity_id, lock=True)
    return bool(
        record is not None and record["deactivated_at"] is None
        and str(record["version_id"]) == event.payload["version_id"]
        and expiry_is_due(record["valid_to"], now)
        and record["valid_to"].isoformat() == event.payload["valid_to"]
    )
