"""Expose durable notification backlog on the event-worker metrics endpoint."""

import asyncio
from datetime import UTC, datetime

from infrastructure.database import AsyncSessionLocal
from infrastructure.logging import log_event
from infrastructure.metrics import (
    NOTIFICATION_EMAIL_AGE,
    NOTIFICATION_EMAIL_BACKLOG,
    NOTIFICATION_OUTBOX_AGE,
    NOTIFICATION_OUTBOX_BACKLOG,
)
from infrastructure.repositories import notification_email_repository as emails
from infrastructure.repositories import notification_outbox_repository as outbox


async def refresh_backlog() -> None:
    async with AsyncSessionLocal() as session:
        events = await outbox.outbox_stats(session)
        deliveries = await emails.delivery_stats(session, datetime.now(UTC))
    NOTIFICATION_OUTBOX_BACKLOG.set(events["backlog"])
    NOTIFICATION_OUTBOX_AGE.set(events["oldest_age_seconds"])
    NOTIFICATION_EMAIL_BACKLOG.set(deliveries["backlog"])
    NOTIFICATION_EMAIL_AGE.set(deliveries["oldest_age_seconds"])
    log_event(
        "info",
        "notification.backlog",
        "Notification delivery backlog",
        outbox_backlog=events["backlog"],
        outbox_oldest_age_seconds=events["oldest_age_seconds"],
        email_backlog=deliveries["backlog"],
        email_oldest_age_seconds=deliveries["oldest_age_seconds"],
    )


async def run_backlog_collector() -> None:
    while True:
        try:
            await refresh_backlog()
        except Exception as exc:
            log_event(
                "warning",
                "notification.backlog.failed",
                "Notification backlog collection failed",
                error_code=type(exc).__name__,
            )
        await asyncio.sleep(30)
