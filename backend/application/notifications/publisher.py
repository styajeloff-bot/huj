"""Durable Kafka publisher; its journal is PostgreSQL, never the Redis queue."""

import asyncio
from contextlib import suppress
from datetime import UTC, datetime
from typing import Any

from infrastructure.database import AsyncSessionLocal
from infrastructure.logging import bind_log_context, log_event
from infrastructure.messaging.broker import get_broker
from infrastructure.messaging.topics import NOTIFICATION_EVENTS
from infrastructure.metrics import NOTIFICATION_EVENTS as EVENT_METRIC
from infrastructure.repositories import notification_outbox_repository as repo
from infrastructure.settings import settings

_connection_lock = asyncio.Lock()


async def _publish(payload: dict[str, Any]) -> None:
    kafka = get_broker()
    # connect() is idempotent once connected and can retry a failed startup.
    # Serialize first connection when several scheduled/wakeup tasks coincide.
    async with _connection_lock:
        try:
            await kafka.connect()
        except Exception:
            # A failed initial connect can leave a partially started producer.
            with suppress(Exception):
                await kafka.stop()
            raise
    await kafka.publish(
        payload, topic=NOTIFICATION_EVENTS, key=payload["aggregate_id"].encode()
    )


async def publish_outbox_batch() -> dict[str, int]:
    sent, failed = 0, 0
    async with AsyncSessionLocal() as session:
        events = await repo.claim_events(
            session, limit=settings.notification_batch_size, now=datetime.now(UTC)
        )
        for event in events:
            payload = event["payload"]
            try:
                with bind_log_context(correlation_id=payload.get("correlation_id")):
                    await asyncio.wait_for(
                        _publish(payload),
                        timeout=10,
                    )
            except Exception as exc:
                failed += 1
                EVENT_METRIC.labels(stage="publish_failed").inc()
                await repo.publish_failed(
                    session,
                    event["event_id"],
                    event["publish_attempts"],
                    type(exc).__name__,
                    datetime.now(UTC),
                )
                log_event(
                    "warning",
                    "notification.outbox.publish_failed",
                    "Notification remains in outbox",
                    event_id=str(event["event_id"]),
                    error_code=type(exc).__name__,
                )
            else:
                sent += 1
                EVENT_METRIC.labels(stage="published").inc()
                await repo.published(session, event["event_id"], datetime.now(UTC))
        await session.commit()
    return {"published": sent, "failed": failed}
