"""Transport durability at public publisher/consumer seams with real Postgres."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
import sqlalchemy as sa
from aiokafka import ConsumerRecord, TopicPartition
from faststream.kafka import TestKafkaBroker
from faststream.kafka.message import KafkaAckableMessage
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from application import notification_events as consumer
from application.commands.notifications import (
    DeleteNotificationCommand,
    handle_delete_notification,
)
from application.notifications import publisher
from application.notifications.events import record_notification_event
from domain.events.notifications import NotificationEvent
from infrastructure.messaging.topics import NOTIFICATION_EVENTS, NOTIFICATION_EVENTS_DLQ
from infrastructure.models.applications import LeasingApplication
from infrastructure.models.companies import Company
from infrastructure.models.misc import Notification
from infrastructure.models.notification_delivery import (
    NotificationEmailDelivery,
    NotificationEventOutbox,
    NotificationEventReceipt,
)
from infrastructure.models.users import User


@pytest_asyncio.fixture
async def transport_db(
    _engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[dict[str, Any]]:
    factory = async_sessionmaker(_engine, expire_on_commit=False)
    state: dict[str, Any] = {
        "factory": factory,
        "events": [],
        "applications": [],
        "users": [],
        "companies": [],
    }
    monkeypatch.setattr(publisher, "AsyncSessionLocal", factory)
    monkeypatch.setattr(consumer, "AsyncSessionLocal", factory)
    yield state
    async with factory() as session:
        for model, ids, column in [
            (
                NotificationEmailDelivery,
                state["events"],
                NotificationEmailDelivery.event_id,
            ),
            (Notification, state["events"], Notification.event_id),
            (
                NotificationEventReceipt,
                state["events"],
                NotificationEventReceipt.event_id,
            ),
            (
                NotificationEventOutbox,
                state["events"],
                NotificationEventOutbox.event_id,
            ),
            (LeasingApplication, state["applications"], LeasingApplication.id),
            (User, state["users"], User.id),
            (Company, state["companies"], Company.id),
        ]:
            if ids:
                await session.execute(sa.delete(model).where(column.in_(ids)))
        await session.commit()


def _event(
    state: dict[str, Any], aggregate_id: UUID | None = None
) -> NotificationEvent:
    aggregate_id = aggregate_id or uuid4()
    event = NotificationEvent(
        event_id=uuid4(),
        event_type="leasing.application_cancelled",
        entity_type="leasing_application",
        entity_id=aggregate_id,
        aggregate_id=aggregate_id,
        application_id=aggregate_id,
        request_number="TZ35-transport",
        occurred_at=datetime.now(UTC),
        changed_fields=["status"],
        previous_values={"status": "active"},
        new_values={"status": "rejected"},
    )
    state["events"].append(event.event_id)
    return event


async def _append(
    state: dict[str, Any], aggregate_id: UUID,
    event_type: str = "leasing.application_cancelled",
) -> UUID:
    async with state["factory"]() as session:
        event_id = await record_notification_event(
            session,
            event_type=event_type,
            entity_type="monetization_capture" if event_type.startswith("monetization.") else "leasing_application",
            entity_id=aggregate_id,
            aggregate_id=aggregate_id,
            application_id=None if event_type.startswith("monetization.") else aggregate_id,
            request_number="TZ35-transport",
            previous_values={"status": "active"},
            new_values={"status": "rejected"},
            payload={"reason": "Условия монетизации не найдены"} if event_type.startswith("monetization.") else None,
        )
        await session.commit()
    assert event_id is not None
    state["events"].append(event_id)
    return event_id


class RecordingConsumer:
    def __init__(self, state: dict[str, Any], event_id: UUID | None = None) -> None:
        self.state, self.event_id = state, event_id
        self.commits = 0
        self.seeks: list[tuple[TopicPartition, int]] = []

    async def commit(self) -> None:
        if self.event_id is not None:
            # An independent connection must see the receipt before Kafka can
            # advance. An uncommitted row in the handler session is not enough.
            async with self.state["factory"]() as session:
                assert (
                    await session.get(NotificationEventReceipt, self.event_id)
                    is not None
                )
        self.commits += 1

    def seek(self, partition: TopicPartition, offset: int) -> None:
        self.seeks.append((partition, offset))


def _message(body: bytes, kafka: RecordingConsumer) -> KafkaAckableMessage:
    raw = ConsumerRecord(
        topic=NOTIFICATION_EVENTS,
        partition=1,
        offset=42,
        timestamp=1,
        timestamp_type=0,
        key=b"aggregate",
        value=body,
        checksum=None,
        serialized_key_size=9,
        serialized_value_size=len(body),
        headers=[],
    )
    return KafkaAckableMessage(
        raw_message=raw, body=body, consumer=kafka, correlation_id="notification-test"
    )


@pytest.mark.asyncio
async def test_consumer_commits_database_before_advancing_kafka_offset(
    transport_db: dict[str, Any],
) -> None:
    event = _event(transport_db)
    kafka = RecordingConsumer(transport_db, event.event_id)
    await consumer.consume_notification_event(
        event.model_dump(mode="json"), _message(b"{}", kafka)
    )
    assert kafka.commits == 1 and kafka.seeks == []


@pytest.mark.asyncio
async def test_failed_database_commit_rolls_back_and_rewinds_kafka(
    transport_db: dict[str, Any],
    _engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FailingCommitSession(AsyncSession):
        async def commit(self) -> None:
            raise RuntimeError("simulated commit failure")

    monkeypatch.setattr(
        consumer,
        "AsyncSessionLocal",
        async_sessionmaker(_engine, class_=FailingCommitSession),
    )
    event = _event(transport_db)
    kafka = RecordingConsumer(transport_db, event.event_id)
    with pytest.raises(RuntimeError, match="commit failure"):
        await consumer.consume_notification_event(
            event.model_dump(mode="json"), _message(b"{}", kafka)
        )
    assert kafka.commits == 0
    assert kafka.seeks == [(TopicPartition(NOTIFICATION_EVENTS, 1), 42)]
    async with transport_db["factory"]() as session:
        assert await session.get(NotificationEventReceipt, event.event_id) is None


@pytest.mark.asyncio
async def test_poison_raw_json_goes_to_sanitized_dlq_before_ack(
    transport_db: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    published: list[dict] = []

    async def publish(body: dict, *, topic: str) -> None:
        assert topic == NOTIFICATION_EVENTS_DLQ
        published.append(body)

    monkeypatch.setattr(consumer.broker, "publish", publish)
    kafka = RecordingConsumer(transport_db)
    raw = b'{"password": "never-echo-this", INVALID'
    message = _message(raw, kafka)
    await consumer.consume_notification_event(raw, message)
    assert kafka.commits == 1 and kafka.seeks == []
    assert len(published) == 1
    assert published[0]["offset"] == 42 and published[0]["partition"] == 1
    assert "never-echo-this" not in str(published)


@pytest.mark.asyncio
async def test_dlq_outage_does_not_ack_the_poison_message(
    transport_db: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        consumer.broker,
        "publish",
        AsyncMock(side_effect=ConnectionError("broker down")),
    )
    kafka = RecordingConsumer(transport_db)
    with pytest.raises(ConnectionError):
        await consumer.consume_notification_event(
            b"bad-json", _message(b"bad-json", kafka)
        )
    assert kafka.commits == 0
    assert kafka.seeks == [(TopicPartition(NOTIFICATION_EVENTS, 1), 42)]


@pytest.mark.asyncio
async def test_dlq_does_not_echo_unknown_field_names(
    transport_db: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    publish = AsyncMock()
    monkeypatch.setattr(consumer.broker, "publish", publish)
    kafka = RecordingConsumer(transport_db)
    event = _event(transport_db).model_dump(mode="json")
    event["secret-person@example.test"] = "sensitive-value"
    await consumer.consume_notification_event(event, _message(b"{}", kafka))
    assert kafka.commits == 1
    assert "secret-person" not in str(publish.call_args)
    assert "sensitive-value" not in str(publish.call_args)


@pytest.mark.asyncio
async def test_registered_faststream_decoder_routes_invalid_json_to_handler_dlq(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exercise the installed framework parser, not just a direct Python call."""
    dead_letters: list[dict] = []
    async with TestKafkaBroker(consumer.broker):
        original_publish = consumer.broker.publish

        async def publish(body: Any, *, topic: str, **kwargs: Any) -> Any:
            if topic == NOTIFICATION_EVENTS_DLQ:
                dead_letters.append(body)
                return None
            return await original_publish(body, topic=topic, **kwargs)

        monkeypatch.setattr(consumer.broker, "publish", publish)
        await consumer.broker.publish(
            b'{"secret":"do-not-copy",',
            topic=NOTIFICATION_EVENTS,
            headers={"content-type": "application/json"},
        )
    assert len(dead_letters) == 1
    assert dead_letters[0]["errors"][0]["type"] == "json_invalid"
    assert "do-not-copy" not in str(dead_letters)


@pytest.mark.asyncio
@pytest.mark.parametrize("event_type", ["leasing.application_cancelled", "monetization.capture_failed"])
async def test_publisher_failure_keeps_event_due_for_a_later_retry(
    transport_db: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    event_type: str,
) -> None:
    event_id = await _append(transport_db, uuid4(), event_type)
    broker = AsyncMock()
    broker.publish.side_effect = ConnectionError("secret must not be persisted")
    monkeypatch.setattr(publisher, "get_broker", lambda: broker)
    assert await publisher.publish_outbox_batch() == {"published": 0, "failed": 1}
    async with transport_db["factory"]() as session:
        row = await session.get(NotificationEventOutbox, event_id)
        assert (
            row is not None and row.published_at is None and row.publish_attempts == 1
        )
        assert row.last_publish_error == "ConnectionError"
        assert row.next_attempt_at > datetime.now(UTC)
        row.next_attempt_at = datetime.now(UTC) - timedelta(seconds=1)
        await session.commit()
    broker.publish.side_effect = None
    assert await publisher.publish_outbox_batch() == {"published": 1, "failed": 0}
    async with transport_db["factory"]() as session:
        row = await session.get(NotificationEventOutbox, event_id)
        assert (
            row is not None
            and row.published_at is not None
            and row.publish_attempts == 2
        )


@pytest.mark.asyncio
async def test_publisher_recovers_when_kafka_was_unavailable_at_worker_start(
    transport_db: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    event_id = await _append(transport_db, uuid4())
    broker = AsyncMock()
    broker.connect.side_effect = ConnectionError("startup outage")
    monkeypatch.setattr(publisher, "get_broker", lambda: broker)
    assert await publisher.publish_outbox_batch() == {"published": 0, "failed": 1}
    broker.publish.assert_not_awaited()
    broker.stop.assert_awaited_once()
    async with transport_db["factory"]() as session:
        row = await session.get(NotificationEventOutbox, event_id)
        assert row is not None
        row.next_attempt_at = datetime.now(UTC) - timedelta(seconds=1)
        await session.commit()
    broker.connect.side_effect = None
    assert await publisher.publish_outbox_batch() == {"published": 1, "failed": 0}
    broker.publish.assert_awaited_once()


@pytest.mark.asyncio
async def test_parallel_publishers_cannot_overtake_the_first_aggregate_event(
    transport_db: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    aggregate = uuid4()
    first_id = await _append(transport_db, aggregate)
    second_id = await _append(transport_db, aggregate)
    entered, release = asyncio.Event(), asyncio.Event()
    observed: list[str] = []

    async def publish(body: dict, *, topic: str, key: bytes) -> None:
        assert topic == NOTIFICATION_EVENTS and key == str(aggregate).encode()
        if body["event_id"] == str(first_id):
            entered.set()
            await release.wait()
        observed.append(body["event_id"])

    broker = AsyncMock()
    broker.publish.side_effect = publish
    monkeypatch.setattr(publisher, "get_broker", lambda: broker)
    first = asyncio.create_task(publisher.publish_outbox_batch())
    try:
        await asyncio.wait_for(entered.wait(), timeout=2)
        concurrent = await asyncio.wait_for(publisher.publish_outbox_batch(), timeout=2)
        assert concurrent == {"published": 0, "failed": 0}
        assert observed == []
    finally:
        release.set()
        await first
    assert await publisher.publish_outbox_batch() == {"published": 1, "failed": 0}
    assert observed == [str(first_id), str(second_id)]


@pytest.mark.asyncio
async def test_deleted_inbox_is_not_recreated_by_consumer_replay(
    transport_db: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from application.tasks.notifications import recover_email_deliveries

    monkeypatch.setattr(recover_email_deliveries, "kiq", AsyncMock())
    async with transport_db["factory"]() as session:
        company = Company(name="Replay client", company_type="other", is_active=True)
        session.add(company)
        await session.flush()
        user = User(
            phone=f"+7{uuid4().int % 10**16:016d}",
            role="client",
            company_id=company.id,
            is_active=True,
        )
        session.add(user)
        await session.flush()
        app = LeasingApplication(
            company_id=company.id, created_by=user.id, status="rejected"
        )
        session.add(app)
        await session.commit()
        transport_db["companies"].append(company.id)
        transport_db["users"].append(user.id)
        transport_db["applications"].append(app.id)
    event = _event(transport_db, app.id)
    kafka = RecordingConsumer(transport_db, event.event_id)
    await consumer.consume_notification_event(
        event.model_dump(mode="json"), _message(b"{}", kafka)
    )
    async with transport_db["factory"]() as session:
        row = await session.scalar(
            sa.select(Notification).where(Notification.event_id == event.event_id)
        )
        assert row is not None
        notification_id = row.id
        await handle_delete_notification(
            DeleteNotificationCommand(user_id=user.id, notification_id=row.id), session
        )
        await session.commit()
    await consumer.consume_notification_event(
        event.model_dump(mode="json"), _message(b"{}", kafka)
    )
    async with transport_db["factory"]() as session:
        rows = (
            await session.scalars(
                sa.select(Notification).where(Notification.event_id == event.event_id)
            )
        ).all()
        assert (
            len(rows) == 1
            and rows[0].id == notification_id
            and rows[0].deleted_at is not None
        )
        assert (
            await session.scalar(
                sa.select(sa.func.count())
                .select_from(NotificationEmailDelivery)
                .where(
                    NotificationEmailDelivery.event_id == event.event_id,
                )
            )
            == 1
        )
    assert kafka.commits == 2
