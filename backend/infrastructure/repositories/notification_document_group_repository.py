"""Transactional ten-minute groups for requested-document upload facts only.

All mutations acquire the same scope advisory lock. There is no network I/O
while it is held: receipt/member insertion and group/summary closing are each
one caller-owned transaction, so a crash releases locks and rolls back work.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from domain.events.notifications import NotificationEvent
from infrastructure.models.applications import LeasingCompanyApplication
from infrastructure.models.companies import Company, LeasingCompany
from infrastructure.models.documents import (
    ApplicationDocument,
    ApplicationDocumentRequest,
)
from infrastructure.models.notification_delivery import (
    NotificationDocumentUploadGroup as Group,
)
from infrastructure.models.notification_delivery import (
    NotificationDocumentUploadMember as Member,
)


def _scope_key(
    application_id: UUID, leasing_company_id: UUID, request_batch_id: UUID
) -> str:
    return f"document-upload:{application_id}:{leasing_company_id}:{request_batch_id}"


async def include_upload(session: AsyncSession, event: NotificationEvent) -> bool:
    """True consumes a grouped/rejected fact; False retains legacy individual notice.

    Resolve the request batch from PostgreSQL even for a payload that supplies it.
    Missing historical identity falls back safely, contradictory current identity
    is rejected rather than joining a different application's or LC's batch.
    """
    request_id = event.payload.get("document_request_id")
    document_id = event.payload.get("document_id")
    if not request_id or not document_id:
        return False
    request = await session.get(ApplicationDocumentRequest, UUID(request_id))
    if request is None:
        return False
    batch_id = event.payload.get("request_batch_id")
    if (
        request.application_id != event.application_id
        or str(request.leasing_company_id) != event.payload["leasing_company_id"]
        or (batch_id is not None and str(request.request_batch_id) != batch_id)
    ):
        return True
    linked_document = await session.scalar(
        select(ApplicationDocument.id)
        .join(
            LeasingCompanyApplication,
            (
                LeasingCompanyApplication.application_id
                == ApplicationDocument.application_id
            )
            & (
                LeasingCompanyApplication.leasing_company_id
                == ApplicationDocument.leasing_company_id
            ),
        )
        .join(
            LeasingCompany, LeasingCompany.id == ApplicationDocument.leasing_company_id
        )
        .join(Company, Company.id == LeasingCompany.company_id)
        .where(
            ApplicationDocument.application_id == request.application_id,
            ApplicationDocument.leasing_company_id == request.leasing_company_id,
            ApplicationDocument.document_request_id == request.id,
            ApplicationDocument.document_id == UUID(document_id),
            LeasingCompany.is_active.is_(True),
            Company.is_active.is_(True),
        )
    )
    if linked_document is None:
        return True
    await session.execute(
        select(
            func.pg_advisory_xact_lock(
                func.hashtextextended(
                    _scope_key(
                        request.application_id,
                        request.leasing_company_id,
                        request.request_batch_id,
                    ),
                    35,
                )
            )
        )
    )
    if await session.get(Member, event.event_id) is not None:
        return True
    later_open_group = False
    # A closed snapshot is never changed. Delayed facts instead open their own
    # persistent batch with an original-event due time, not now + ten minutes.
    group = await session.scalar(
        select(Group)
        .where(
            Group.application_id == request.application_id,
            Group.leasing_company_id == request.leasing_company_id,
            Group.request_batch_id == request.request_batch_id,
            Group.closed_at.is_(None),
            Group.first_upload_at <= event.occurred_at,
            Group.closes_at > event.occurred_at,
        )
        .order_by(Group.created_at, Group.id)
        .limit(1)
    )
    if group is None:
        later_open_group = bool(
            await session.scalar(
                select(Group.id)
                .where(
                    Group.application_id == request.application_id,
                    Group.leasing_company_id == request.leasing_company_id,
                    Group.request_batch_id == request.request_batch_id,
                    Group.closed_at.is_(None),
                    Group.first_upload_at > event.occurred_at,
                )
                .limit(1)
            )
        )
        group = Group(
            application_id=request.application_id,
            leasing_company_id=request.leasing_company_id,
            request_batch_id=request.request_batch_id,
            first_event_id=event.event_id,
            request_number=event.request_number,
            first_upload_at=event.occurred_at,
            closes_at=event.occurred_at + timedelta(minutes=10),
        )
        session.add(group)
        await session.flush()
    await session.execute(
        insert(Member)
        .values(
            event_id=event.event_id,
            group_id=group.id,
            document_id=UUID(document_id),
            occurred_at=event.occurred_at,
        )
        .on_conflict_do_nothing()
    )
    if later_open_group:
        await _repartition_open_groups(session, request)
    return True


async def _repartition_open_groups(
    session: AsyncSession,
    request: ApplicationDocumentRequest,
) -> None:
    """Late earlier timestamps may shorten pending windows, never extend them.

    Only unclosed groups are mutable. Repartition their source facts in event-time
    order so reversed Kafka delivery cannot create overlapping pending windows or
    incorrect document counts. Closed snapshots are never selected or rewritten.
    """
    pending = list(
        (
            await session.scalars(
                select(Group).where(
                    Group.application_id == request.application_id,
                    Group.leasing_company_id == request.leasing_company_id,
                    Group.request_batch_id == request.request_batch_id,
                    Group.closed_at.is_(None),
                )
            )
        ).all()
    )
    by_first_event = {group.first_event_id: group for group in pending}
    facts = (
        await session.execute(
            select(Member.event_id, Member.occurred_at)
            .where(
                Member.group_id.in_([group.id for group in pending]),
            )
            .order_by(Member.occurred_at, Member.event_id)
        )
    ).all()
    retained: set[UUID] = set()
    current: Group | None = None
    for event_id, occurred_at in facts:
        if current is None or occurred_at >= current.closes_at:
            current = by_first_event.get(event_id)
            if current is None:
                current = Group(
                    application_id=request.application_id,
                    leasing_company_id=request.leasing_company_id,
                    request_batch_id=request.request_batch_id,
                    first_event_id=event_id,
                    request_number=pending[0].request_number,
                    first_upload_at=occurred_at,
                    closes_at=occurred_at + timedelta(minutes=10),
                )
                session.add(current)
                await session.flush()
            retained.add(current.id)
        await session.execute(
            update(Member)
            .where(Member.event_id == event_id)
            .values(group_id=current.id)
        )
    redundant = [group.id for group in pending if group.id not in retained]
    if redundant:
        # These technical rows have no summary/inbox yet; all source facts have
        # just moved to their correct pending windows under the same scope lock.
        await session.execute(
            delete(Group).where(Group.id.in_(redundant), Group.closed_at.is_(None))
        )


async def close_due_groups(
    session: AsyncSession,
    now: datetime,
    *,
    limit: int,
) -> list[dict[str, Any]]:
    """Fence with scope locks and return frozen summaries for atomic outbox writes.

    No lease can expire mid-finalization: the transaction owns its locks until the
    summary is committed. Competing sweeps skip busy scopes and recover next run.
    """
    candidates = (
        await session.execute(
            select(
                Group.id,
                Group.application_id,
                Group.leasing_company_id,
                Group.request_batch_id,
            )
            .where(Group.closed_at.is_(None), Group.closes_at <= now)
            .order_by(Group.closes_at, Group.id)
            .limit(limit)
        )
    ).all()
    result = []
    for group_id, application_id, lc_id, batch_id in candidates:
        locked = await session.scalar(
            select(
                func.pg_try_advisory_xact_lock(
                    func.hashtextextended(
                        _scope_key(application_id, lc_id, batch_id), 35
                    ),
                )
            )
        )
        if not locked:
            continue
        # Re-read after the scope lock: another sweep may have committed while
        # candidates were loaded. populate_existing defeats stale identity maps.
        group = await session.scalar(
            select(Group)
            .where(
                Group.id == group_id,
                Group.closed_at.is_(None),
                Group.closes_at <= now,
            )
            .execution_options(populate_existing=True)
        )
        if group is None:
            continue
        count, last_upload_at = (
            await session.execute(
                select(
                    func.count(Member.document_id.distinct()),
                    func.max(Member.occurred_at),
                ).where(Member.group_id == group_id)
            )
        ).one()
        if not count:
            raise ValueError(
                "Document upload group cannot be closed without source facts"
            )
        group.closed_at = now
        result.append(
            {
                "group_id": group.id,
                "application_id": group.application_id,
                "request_number": group.request_number,
                "payload": {
                    "group_id": str(group.id),
                    "leasing_company_id": str(group.leasing_company_id),
                    "request_batch_id": str(group.request_batch_id),
                    "document_count": count,
                    "first_upload_at": group.first_upload_at.isoformat(),
                    "last_upload_at": last_upload_at.isoformat(),
                    "closes_at": group.closes_at.isoformat(),
                },
                "closes_at": group.closes_at,
            }
        )
    await session.flush()
    return result


async def summary_matches_closed_group(
    session: AsyncSession,
    event: NotificationEvent,
) -> bool:
    """Kafka payloads cannot invent a summary or widen its persisted snapshot."""
    group = await session.get(Group, event.event_id)
    if (
        group is None
        or group.closed_at is None
        or group.application_id != event.application_id
        or str(group.leasing_company_id) != event.payload["leasing_company_id"]
        or str(group.request_batch_id) != event.payload["request_batch_id"]
        or group.request_number != event.request_number
        or group.first_upload_at
        != datetime.fromisoformat(event.payload["first_upload_at"])
        or group.closes_at != datetime.fromisoformat(event.payload["closes_at"])
    ):
        return False
    count, last_upload_at = (
        await session.execute(
            select(
                func.count(Member.document_id.distinct()),
                func.max(Member.occurred_at),
            ).where(Member.group_id == group.id)
        )
    ).one()
    return count == event.payload[
        "document_count"
    ] and last_upload_at == datetime.fromisoformat(event.payload["last_upload_at"])
