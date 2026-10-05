"""Taskiq executes/retries durable notification work; Kafka carries the facts."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from application.notifications.document_grouping import finalize_document_upload_groups
from application.notifications.email_delivery import deliver_email
from application.notifications.publisher import publish_outbox_batch
from infrastructure.database import AsyncSessionLocal
from infrastructure.repositories import notification_outbox_repository as outbox
from infrastructure.settings import settings
from infrastructure.taskiq_broker import broker


@broker.task(task_name="notifications.publish_outbox", schedule=[{"cron": "* * * * *"}])
async def publish_outbox() -> None:
    # Multiple rounds drain same-aggregate successors while maintaining order.
    for _ in range(10):
        result = await publish_outbox_batch()
        if not result["published"]:
            break


@broker.task(task_name="notifications.send_email")
async def send_notification_email(delivery_id: UUID) -> None:
    await deliver_email(delivery_id)


@broker.task(
    task_name="notifications.close_document_upload_groups", schedule=[{"cron": "* * * * *"}],
)
async def close_document_upload_groups() -> None:
    async with AsyncSessionLocal() as session:
        await finalize_document_upload_groups(
            session, datetime.now(UTC), limit=settings.notification_batch_size,
        )
        await session.commit()
    await publish_outbox()


@broker.task(
    task_name="notifications.recover_email_deliveries", schedule=[{"cron": "* * * * *"}]
)
async def recover_email_deliveries() -> None:
    # Immediate, daily and weekly due times are persisted on each intent. This
    # single sweep also recovers missed digest schedules after downtime.
    for _ in range(settings.notification_batch_size):
        if await deliver_email() == "idle":
            break


@broker.task(task_name="notifications.scan_deadlines", schedule=[{"cron": "* * * * *"}])
async def scan_deadlines() -> None:
    from application.notifications.exchange_deadlines import scan_exchange_deadlines
    from application.notifications.exchange_events import (
        publish_finalized_exchange_snapshots,
    )
    from application.notifications.leasing_deadlines import (
        scan_leasing_reservation_deadlines,
    )

    async with AsyncSessionLocal() as session:
        now = datetime.now(UTC)
        await scan_exchange_deadlines(session, now)
        await scan_leasing_reservation_deadlines(session, now)
        finalized_ids = session.info.pop("notification_exchange_finalized_ids", [])
        await session.commit()
    await publish_finalized_exchange_snapshots(finalized_ids)
    await publish_outbox()


@broker.task(
    task_name="notifications.scan_document_registry_expiries",
    schedule=[{"cron": "0 * * * *"}],
)
async def scan_document_registry_expiries() -> None:
    from application.notifications.document_registry_expiry import (
        scan_document_registry_expiries as scan_expiries,
    )

    async with AsyncSessionLocal() as session:
        await scan_expiries(session, datetime.now(UTC))
        await session.commit()
    await publish_outbox()


@broker.task(task_name="notifications.cleanup", schedule=[{"cron": "17 3 * * *"}])
async def cleanup() -> None:
    async with AsyncSessionLocal() as session:
        await outbox.cleanup_published(
            session,
            before=datetime.now(UTC)
            - timedelta(days=settings.notification_outbox_retention_days),
        )
        await session.commit()
