"""Outbox SQL and durable consumer receipts; caller owns commit."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import delete, exists, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from domain.events.notifications import NotificationEvent
from infrastructure.models.notification_delivery import (
    NotificationEventOutbox,
    NotificationEventReceipt,
)


async def append_event(session: AsyncSession, event: NotificationEvent) -> UUID | None:
    # Serialize producers of the same aggregate before assigning its sequence.
    await session.execute(
        select(
            func.pg_advisory_xact_lock(
                func.hashtextextended(str(event.aggregate_id), 35)
            )
        )
    )
    stmt = (
        insert(NotificationEventOutbox)
        .values(
            event_id=event.event_id,
            event_type=event.event_type,
            entity_type=event.entity_type,
            entity_id=event.entity_id,
            aggregate_id=event.aggregate_id,
            occurrence_key=event.occurrence_key,
            payload=event.model_dump(mode="json"),
            occurred_at=event.occurred_at,
        )
        .on_conflict_do_nothing()
        .returning(NotificationEventOutbox.event_id)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def claim_events(
    session: AsyncSession, *, limit: int, now: datetime
) -> list[dict[str, Any]]:
    previous = aliased(NotificationEventOutbox)
    # SKIP LOCKED alone could let publisher B overtake publisher A. Only the
    # earliest unpublished event of each aggregate may become publishable.
    stmt = (
        select(NotificationEventOutbox)
        .where(
            NotificationEventOutbox.published_at.is_(None),
            NotificationEventOutbox.next_attempt_at <= now,
            ~exists(
                select(previous.event_id).where(
                    previous.aggregate_id == NotificationEventOutbox.aggregate_id,
                    previous.published_at.is_(None),
                    previous.sequence < NotificationEventOutbox.sequence,
                )
            ),
        )
        .order_by(NotificationEventOutbox.sequence)
        .with_for_update(skip_locked=True)
        .limit(limit)
    )
    return [
        {
            "event_id": row.event_id,
            "payload": row.payload,
            "publish_attempts": row.publish_attempts,
        }
        for row in (await session.scalars(stmt)).all()
    ]


async def published(session: AsyncSession, event_id: UUID, now: datetime) -> None:
    await session.execute(
        update(NotificationEventOutbox)
        .where(NotificationEventOutbox.event_id == event_id)
        .values(
            published_at=now,
            publish_attempts=NotificationEventOutbox.publish_attempts + 1,
            last_publish_error=None,
        )
    )


async def publish_failed(
    session: AsyncSession, event_id: UUID, attempts: int, error: str, now: datetime
) -> None:
    await session.execute(
        update(NotificationEventOutbox)
        .where(NotificationEventOutbox.event_id == event_id)
        .values(
            publish_attempts=attempts + 1,
            last_publish_error=error[:250],
            next_attempt_at=now
            + timedelta(seconds=min(3600, 5 * 2 ** min(attempts, 10))),
        )
    )


async def receive_once(session: AsyncSession, event: NotificationEvent) -> bool:
    """Insert a receipt in the same transaction as every user's delivery intent."""
    result = await session.execute(
        insert(NotificationEventReceipt)
        .values(
            event_id=event.event_id,
            payload=event.model_dump(mode="json"),
        )
        .on_conflict_do_nothing()
        .returning(NotificationEventReceipt.event_id)
    )
    return result.scalar_one_or_none() is not None


async def cleanup_published(session: AsyncSession, *, before: datetime) -> int:
    # Scheduled occurrence keys must remain durable beyond Kafka retention.
    result = await session.execute(
        delete(NotificationEventOutbox)
        .where(
            NotificationEventOutbox.published_at < before,
            NotificationEventOutbox.occurrence_key.is_(None),
        )
        .returning(NotificationEventOutbox.event_id)
    )
    return len(result.all())


async def outbox_stats(session: AsyncSession) -> dict[str, Any]:
    row = (
        await session.execute(
            select(func.count(), func.min(NotificationEventOutbox.created_at)).where(
                NotificationEventOutbox.published_at.is_(None),
            )
        )
    ).one()
    return {
        "backlog": row[0],
        "oldest_age_seconds": max(0, (datetime.now(UTC) - row[1]).total_seconds())
        if row[1]
        else 0,
    }
