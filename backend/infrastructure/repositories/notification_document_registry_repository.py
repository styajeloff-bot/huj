"""Expiry projection for the document registry; transactions belong to callers."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import exists, select, union_all, update
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.models.document_registry import (
    document_group_participants as participants,
)
from infrastructure.models.document_registry import (
    document_groups as groups,
)
from infrastructure.models.document_registry import (
    reference_document_related_companies as related,
)
from infrastructure.models.document_registry import (
    reference_document_types as types,
)
from infrastructure.models.document_registry import (
    reference_document_versions as versions,
)
from infrastructure.models.document_registry import (
    reference_documents as documents,
)
from infrastructure.models.notification_delivery import (
    NotificationEventOutbox,
    NotificationEventReceipt,
)


def _live_group() -> Any:
    main = documents.alias("main_document")
    return exists(select(main.c.id).where(
        main.c.group_id == documents.c.group_id,
        main.c.is_main.is_(True), main.c.deleted_at.is_(None),
    ))


async def get_document_context(
    session: AsyncSession, document_id: UUID, *, lock: bool = False,
) -> dict[str, Any] | None:
    if lock:
        # Read the projection AFTER obtaining the lock. A joined SELECT FOR
        # SHARE could otherwise retain the version snapshot from before a wait.
        await session.execute(select(documents.c.id).where(
            documents.c.id == document_id,
        ).with_for_update(read=True, of=documents))
    row = (await session.execute(select(
        documents.c.id, documents.c.group_id, documents.c.contract_number,
        documents.c.name, documents.c.deactivated_at,
        documents.c.platform_ml_related, groups.c.platform_ml_participates,
        types.c.display_name.label("document_type"),
        versions.c.id.label("version_id"), versions.c.valid_to,
    ).select_from(documents.join(groups, groups.c.id == documents.c.group_id)
        .join(types, types.c.type_code == documents.c.document_type)
        .join(versions, versions.c.document_id == documents.c.id))
        .where(documents.c.id == document_id, documents.c.deleted_at.is_(None),
            versions.c.is_current.is_(True), _live_group()))).mappings().one_or_none()
    if row is None:
        return None
    result = dict(row)
    company_rows = (await session.execute(union_all(
        select(participants.c.role, participants.c.company_id).where(
            participants.c.group_id == result["group_id"]),
        select(related.c.role, related.c.company_id).where(
            related.c.document_id == document_id),
    ))).all()
    result["company_roles"] = {(role, company_id) for role, company_id in company_rows}
    return result


async def list_due_document_ids(
    session: AsyncSession, today: date, *, after_id: UUID | None = None, limit: int = 200,
) -> list[UUID]:
    stmt = select(documents.c.id).join(
        versions, versions.c.document_id == documents.c.id,
    ).where(
        documents.c.deleted_at.is_(None), documents.c.deactivated_at.is_(None),
        versions.c.is_current.is_(True),
        versions.c.valid_to.between(today, today + timedelta(days=30)),
        _live_group(),
    ).order_by(documents.c.id).limit(limit)
    if after_id is not None:
        stmt = stmt.where(documents.c.id > after_id)
    return list((await session.scalars(stmt)).all())


async def rearm_undelivered_expiry(
    session: AsyncSession, occurrence_key: str, now: datetime,
) -> UUID | None:
    """Explicit activation holds the document lock; successful receipts survive."""
    return (await session.execute(update(NotificationEventOutbox).where(
        NotificationEventOutbox.event_type == "document_registry.expiring",
        NotificationEventOutbox.occurrence_key == occurrence_key,
        ~exists(select(NotificationEventReceipt.event_id).where(
            NotificationEventReceipt.event_id == NotificationEventOutbox.event_id,
        )),
    ).values(published_at=None, next_attempt_at=now, last_publish_error=None)
        .returning(NotificationEventOutbox.event_id))).scalar_one_or_none()
