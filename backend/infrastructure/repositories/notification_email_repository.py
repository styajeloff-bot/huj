"""SMTP journal SQL: short transactions, persisted batches and fenced leases."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.models.misc import Notification
from infrastructure.models.notification_delivery import NotificationEmailBatch as Batch
from infrastructure.models.notification_delivery import (
    NotificationEmailDelivery as Delivery,
)
from infrastructure.models.notification_delivery import (
    NotificationEventReceipt as Receipt,
)


async def create_delivery(session: AsyncSession, **values: Any) -> UUID:
    row = Delivery(**values)
    session.add(row)
    await session.flush()
    return row.id


def _batch_dict(batch: Batch) -> dict[str, Any]:
    return {
        "id": batch.id,
        "user_id": batch.user_id,
        "delivery_mode": batch.delivery_mode,
        "attempt_count": batch.attempt_count,
        "lease_token": batch.lease_token,
        "message_id": batch.message_id,
    }


async def claim_batch(
    session: AsyncSession,
    *,
    now: datetime,
    lease_seconds: int,
    limit: int,
    message_domain: str,
    delivery_id: UUID | None = None,
) -> dict[str, Any] | None:
    due_batches = select(Batch).where(
        or_(
            (Batch.status.in_(["pending", "retry_wait"]))
            & (Batch.next_attempt_at <= now),
            (Batch.status == "processing") & (Batch.lease_until <= now),
        )
    )
    if delivery_id is not None:
        due_batches = due_batches.where(
            Batch.id.in_(select(Delivery.batch_id).where(Delivery.id == delivery_id))
        )
    batch = (
        await session.scalars(
            due_batches.order_by(Batch.next_attempt_at)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
    ).first()
    if batch is None:
        due = select(Delivery.user_id, Delivery.delivery_mode).where(
            Delivery.batch_id.is_(None),
            Delivery.status == "pending",
            Delivery.next_attempt_at <= now,
        )
        if delivery_id is not None:
            due = due.where(Delivery.id == delivery_id)
        first = (
            await session.execute(
                due.order_by(Delivery.next_attempt_at, Delivery.id).limit(1)
            )
        ).first()
        if first is None:
            return None
        locked = await session.scalar(
            select(
                func.pg_try_advisory_xact_lock(
                    func.hashtextextended(
                        f"notification-email:{first.user_id}:{first.delivery_mode}", 36
                    )
                )
            )
        )
        if not locked:
            return None
        members_stmt = (
            select(Delivery.id)
            .where(
                Delivery.user_id == first.user_id,
                Delivery.delivery_mode == first.delivery_mode,
                Delivery.batch_id.is_(None),
                Delivery.status == "pending",
                Delivery.next_attempt_at <= now,
            )
            .order_by(Delivery.next_attempt_at, Delivery.id)
            .with_for_update(skip_locked=True)
            .limit(1 if first.delivery_mode == "immediate" else limit)
        )
        members = list((await session.scalars(members_stmt)).all())
        if not members:
            return None
        batch_id = uuid4()
        batch = Batch(
            id=batch_id,
            user_id=first.user_id,
            delivery_mode=first.delivery_mode,
            message_id=f"<notification-{batch_id}@{message_domain}>",
            attempt_count=0,
        )
        session.add(batch)
        await session.flush()
        await session.execute(
            update(Delivery)
            .where(Delivery.id.in_(members))
            .values(batch_id=batch_id, message_id=batch.message_id)
        )
    batch.status = "processing"
    batch.lease_token = uuid4()
    batch.lease_until = now + timedelta(seconds=lease_seconds)
    await session.flush()
    return _batch_dict(batch)


async def batch_members(session: AsyncSession, batch_id: UUID) -> list[dict[str, Any]]:
    rows = (
        await session.execute(
            select(Delivery, Notification, Receipt.payload)
            .join(
                Notification,
                Notification.id == Delivery.notification_id,
            )
            .join(Receipt, Receipt.event_id == Delivery.event_id)
            .where(
                Delivery.batch_id == batch_id,
                Delivery.status.in_(["pending", "processing", "retry_wait"]),
            )
            .order_by(Notification.created_at, Delivery.id)
        )
    ).all()
    return [
        {
            "id": delivery.id,
            "event_id": delivery.event_id,
            "user_id": delivery.user_id,
            "recipient_role": delivery.recipient_role,
            "recipient_company_id": delivery.recipient_company_id,
            "payload": payload,
            "title": notification.title,
            "message": notification.message,
            "data": notification.data,
            "action_url": notification.action_url,
        }
        for delivery, notification, payload in rows
    ]


async def skip_delivery(
    session: AsyncSession, delivery_id: UUID, reason: str, now: datetime
) -> None:
    await session.execute(
        update(Delivery)
        .where(Delivery.id == delivery_id)
        .values(status=reason, updated_at=now)
    )


async def begin_attempt(
    session: AsyncSession,
    batch_id: UUID,
    token: UUID,
    now: datetime,
    *,
    lease_seconds: int = 600,
) -> int | None:
    attempt = (
        await session.execute(
            update(Batch)
            .where(
                Batch.id == batch_id,
                Batch.lease_token == token,
                Batch.status == "processing",
            )
            .values(
                attempt_count=Batch.attempt_count + 1,
                lease_until=now + timedelta(seconds=lease_seconds),
            )
            .returning(Batch.attempt_count)
        )
    ).scalar_one_or_none()
    if attempt is not None:
        await session.execute(
            update(Delivery)
            .where(
                Delivery.batch_id == batch_id,
                Delivery.status.in_(["pending", "processing", "retry_wait"]),
            )
            .values(
                status="processing",
                processing_started_at=now,
                attempt_count=attempt,
                updated_at=now,
            )
        )
    return attempt


async def reschedule_unattempted_delivery(
    session: AsyncSession,
    delivery_id: UUID,
    mode: str,
    due: datetime,
) -> None:
    await session.execute(
        update(Delivery)
        .where(
            Delivery.id == delivery_id,
            Delivery.attempt_count == 0,
        )
        .values(batch_id=None, message_id=None, delivery_mode=mode, next_attempt_at=due)
    )


async def reschedule_user_pending(
    session: AsyncSession,
    user_id: UUID,
    mode: str,
    due: datetime,
) -> None:
    """Replan also future intents, without mutating an attempted SMTP batch."""
    await session.execute(
        update(Delivery)
        .where(
            Delivery.user_id == user_id,
            Delivery.status == "pending",
            Delivery.attempt_count == 0,
            Delivery.batch_id.is_(None),
        )
        .values(delivery_mode=mode, next_attempt_at=due)
    )


async def complete_batch(
    session: AsyncSession,
    batch_id: UUID,
    token: UUID,
    *,
    status: str,
    now: datetime,
    next_attempt_at: datetime | None = None,
    error: str | None = None,
) -> bool:
    claimed = (
        await session.execute(
            update(Batch)
            .where(
                Batch.id == batch_id,
                Batch.lease_token == token,
                Batch.status == "processing",
            )
            .values(
                status=status,
                lease_token=None,
                lease_until=None,
                next_attempt_at=next_attempt_at or now,
            )
            .returning(Batch.id)
        )
    ).scalar_one_or_none()
    if claimed is None:
        return False
    values: dict[str, Any] = {"status": status, "updated_at": now, "last_error": error}
    if next_attempt_at is not None:
        values["next_attempt_at"] = next_attempt_at
    if status == "sent":
        values["sent_at"] = now
    if status == "failed":
        values["failed_at"] = now
    await session.execute(
        update(Delivery)
        .where(
            Delivery.batch_id == batch_id,
            Delivery.status.in_(["pending", "processing", "retry_wait"]),
        )
        .values(**values)
    )
    return True


async def delivery_stats(session: AsyncSession, now: datetime) -> dict[str, Any]:
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    row = (
        (
            await session.execute(
                select(
                    func.count(Delivery.id).label("total_emails"),
                    func.count(Delivery.id)
                    .filter(Delivery.status == "sent")
                    .label("sent_emails"),
                    func.count(Delivery.id)
                    .filter(Delivery.status == "failed")
                    .label("failed_emails"),
                    func.count(Delivery.id)
                    .filter(Delivery.status.startswith("skipped_"))
                    .label("skipped_emails"),
                    func.count(Delivery.id)
                    .filter(Delivery.sent_at >= midnight)
                    .label("today_emails"),
                    func.count(Delivery.id)
                    .filter(Delivery.sent_at >= now - timedelta(days=7))
                    .label("week_emails"),
                    func.count(Delivery.id)
                    .filter(
                        Delivery.status.in_(["pending", "processing", "retry_wait"])
                    )
                    .label("backlog"),
                    func.min(Delivery.created_at)
                    .filter(
                        Delivery.status.in_(["pending", "processing", "retry_wait"])
                    )
                    .label("oldest"),
                )
            )
        )
        .mappings()
        .one()
    )
    result = dict(row)
    terminal = result["sent_emails"] + result["failed_emails"]
    result["delivery_rate"] = (
        round(100 * result["sent_emails"] / terminal, 2) if terminal else 0.0
    )
    result["oldest_age_seconds"] = (
        max(0, (now - result.pop("oldest")).total_seconds()) if result["oldest"] else 0
    )
    result.pop("oldest", None)
    return result
