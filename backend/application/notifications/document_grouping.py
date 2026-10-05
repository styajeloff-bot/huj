"""Close due requested-document groups through the ordinary outbox transport."""

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from domain.events.notifications import NotificationEvent
from infrastructure.repositories import notification_document_group_repository as groups
from infrastructure.repositories import notification_outbox_repository as outbox


async def finalize_document_upload_groups(
    session: AsyncSession,
    now: datetime,
    *,
    limit: int = 100,
) -> int:
    """Caller commits the immutable group snapshot and summary outbox together."""
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("Document group closing time must be timezone aware")
    snapshots = await groups.close_due_groups(session, now, limit=limit)
    for snapshot in snapshots:
        group_id, application_id = snapshot["group_id"], snapshot["application_id"]
        event = NotificationEvent(
            event_id=group_id,
            event_type="leasing.documents_uploads_summary",
            entity_type="leasing_application",
            entity_id=application_id,
            aggregate_id=application_id,
            application_id=application_id,
            request_number=snapshot["request_number"],
            occurred_at=snapshot["closes_at"],
            occurrence_key=f"leasing.documents_uploads_summary:{group_id}",
            payload=snapshot["payload"],
        )
        await outbox.append_event(session, event)
    return len(snapshots)
