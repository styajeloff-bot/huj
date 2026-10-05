"""Notification repository — returns dicts, never ORM objects."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import TypedDict, cast
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.models.applications import LeasingApplication
from infrastructure.models.misc import Notification
from infrastructure.repository_timing import timed_repository


class NotificationDict(TypedDict, total=False):
    id: UUID
    user_id: UUID | None
    type: str
    title: str
    message: str
    is_read: bool
    application_id: uuid.UUID | None
    application_display_number: str | None
    action_url: str | None
    created_at: datetime | None
    read_at: datetime | None
    data: dict | None
    event_id: UUID | None


def _to_dict(
    row: Notification, *, application_display_number: str | None = None
) -> NotificationDict:
    return NotificationDict(
        id=row.id,
        user_id=row.user_id,
        type=row.type,
        title=row.title,
        message=row.message,
        data=row.data,
        event_id=row.event_id,
        is_read=bool(row.is_read),
        application_id=row.application_id,
        application_display_number=application_display_number,
        action_url=row.action_url,
        created_at=cast("datetime | None", row.created_at),
        read_at=cast("datetime | None", row.read_at),
    )


def _period_cutoff(period: str) -> datetime | None:
    now = datetime.now(UTC).replace(tzinfo=None)
    if period == "today":
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    if period == "week":
        return now - timedelta(days=7)
    if period == "month":
        return now - timedelta(days=30)
    return None


@timed_repository
async def create_notification(
    session: AsyncSession,
    *,
    user_id: UUID,
    notification_type: str,
    title: str,
    message: str,
    application_id: uuid.UUID | None = None,
    action_url: str | None = None,
    data: dict | None = None,
    event_id: UUID | None = None,
) -> UUID:
    row = Notification(
        user_id=user_id,
        type=notification_type,
        title=title,
        message=message,
        application_id=application_id,
        action_url=action_url,
        data=data,
        event_id=event_id,
    )
    session.add(row)
    await session.flush()
    await session.refresh(row)
    return row.id


@timed_repository
async def list_by_user(
    session: AsyncSession,
    user_id: UUID,
    *,
    type_filter: str | None = None,
    is_read: bool | None = None,
    period: str | None = None,
    since: datetime | None = None,
    limit: int = 10,
    offset: int = 0,
) -> tuple[list[NotificationDict], int]:
    conditions = [Notification.user_id == user_id, Notification.deleted_at.is_(None)]
    if type_filter:
        conditions.append(Notification.type == type_filter)
    if is_read is not None:
        conditions.append(Notification.is_read == is_read)
    if period:
        cutoff = _period_cutoff(period)
        if cutoff is not None:
            conditions.append(Notification.created_at >= cutoff)
    if since is not None:
        conditions.append(Notification.created_at > since)

    total_stmt = select(func.count()).select_from(Notification).where(*conditions)
    list_stmt = (
        select(Notification, LeasingApplication.display_number)
        .outerjoin(
            LeasingApplication,
            LeasingApplication.id == Notification.application_id,
        )
        .where(*conditions)
        .order_by(Notification.created_at.desc(), Notification.is_read.asc())
        .limit(limit)
        .offset(offset)
    )

    total = (await session.execute(total_stmt)).scalar_one()
    rows = (await session.execute(list_stmt)).all()
    return [
        _to_dict(notif, application_display_number=display_number)
        for notif, display_number in rows
    ], int(total)


@timed_repository
async def get_counts(session: AsyncSession, user_id: UUID) -> dict[str, int]:
    stmt = select(
        func.count().label("total_count"),
        func.count().filter(Notification.is_read.is_(False)).label("unread_count"),
    ).where(Notification.user_id == user_id, Notification.deleted_at.is_(None))
    row = (await session.execute(stmt)).one()
    return {
        "total_count": int(row.total_count or 0),
        "unread_count": int(row.unread_count or 0),
    }


@timed_repository
async def get_by_id(
    session: AsyncSession, notification_id: UUID
) -> NotificationDict | None:
    row = await session.get(Notification, notification_id)
    return _to_dict(row) if row and row.deleted_at is None else None


@timed_repository
async def mark_as_read(session: AsyncSession, notification_id: UUID) -> None:
    await session.execute(
        update(Notification)
        .where(Notification.id == notification_id, Notification.deleted_at.is_(None))
        .values(is_read=True, read_at=datetime.now(UTC).replace(tzinfo=None))
    )


@timed_repository
async def mark_all_as_read(session: AsyncSession, user_id: UUID) -> int:
    result = await session.execute(
        update(Notification)
        .where(
            Notification.user_id == user_id,
            Notification.is_read.is_(False),
            Notification.deleted_at.is_(None),
        )
        .values(is_read=True, read_at=datetime.now(UTC).replace(tzinfo=None))
        .returning(Notification.id)
    )
    return len(result.scalars().all())


@timed_repository
async def delete_by_id(session: AsyncSession, notification_id: UUID) -> None:
    await session.execute(
        update(Notification)
        .where(Notification.id == notification_id)
        .values(deleted_at=datetime.now(UTC))
    )
