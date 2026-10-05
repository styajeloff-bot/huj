"""Thin Kafka adapter; explicit acknowledgement follows PostgreSQL commit."""

from typing import Any

from faststream.kafka import KafkaMessage
from faststream.middlewares import AckPolicy
from pydantic import ValidationError

from application.notifications.processor import process_notification_event
from application.tasks.notifications import recover_email_deliveries
from domain.events.notifications import NotificationEvent
from infrastructure.database import AsyncSessionLocal
from infrastructure.logging import log_event
from infrastructure.messaging.broker import broker
from infrastructure.messaging.topics import NOTIFICATION_EVENTS, NOTIFICATION_EVENTS_DLQ
from infrastructure.metrics import NOTIFICATION_EVENTS as EVENT_METRIC
from infrastructure.settings import settings


async def _raw_body(message: KafkaMessage) -> bytes:
    # Parsing belongs inside the handler so malformed JSON also reaches DLQ.
    return message.body


@broker.subscriber(
    NOTIFICATION_EVENTS,
    group_id=settings.kafka_notification_consumer_group,
    auto_offset_reset="earliest",
    ack_policy=AckPolicy.MANUAL,
    max_workers=1,
    max_poll_records=1,
    max_poll_interval_ms=900000,
    decoder=_raw_body,
)
async def consume_notification_event(body: Any, message: KafkaMessage) -> None:
    try:
        try:
            event = (
                NotificationEvent.model_validate_json(body)
                if isinstance(body, bytes | str)
                else NotificationEvent.model_validate(body)
            )
        except ValidationError as exc:
            # Do not echo arbitrary poison payloads or PII into logs / DLQ.
            raw = message.raw_message
            if isinstance(raw, tuple):
                raw = raw[0]
            await broker.publish(
                {
                    "source_topic": raw.topic,
                    "partition": raw.partition,
                    "offset": raw.offset,
                    "correlation_id": message.correlation_id,
                    "errors": [
                        {"type": error["type"]}
                        for error in exc.errors(include_input=False)
                    ],
                },
                topic=NOTIFICATION_EVENTS_DLQ,
            )
            await message.ack()
            EVENT_METRIC.labels(stage="dlq").inc()
            log_event(
                "warning",
                "notification.event.invalid",
                "Invalid notification event moved to DLQ",
            )
            return
        async with AsyncSessionLocal() as session:
            delivery_ids = await process_notification_event(session, event)
            await session.commit()
        await message.ack()
    except Exception:
        await message.nack()
        raise
    if delivery_ids:
        try:
            await recover_email_deliveries.kiq()
        except Exception as exc:
            log_event(
                "warning",
                "notification.email.wakeup_failed",
                "Email recovery sweep will retry",
                event_id=str(event.event_id),
                error_code=type(exc).__name__,
            )
