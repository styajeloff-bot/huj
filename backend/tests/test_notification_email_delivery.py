"""Real journal transactions around a fake SMTP boundary."""

import asyncio
import smtplib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import delete, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from application.commands.email_preferences import (
    UpdateEmailPreferencesCommand,
    handle_update_email_preferences,
)
from application.notifications import email_delivery
from application.notifications.processor import process_notification_event
from domain.events.notifications import NotificationEvent
from infrastructure.models.applications import LeasingApplication
from infrastructure.models.companies import Company
from infrastructure.models.email_preferences import EmailPreferences
from infrastructure.models.misc import Notification
from infrastructure.models.notification_delivery import NotificationEmailBatch as Batch
from infrastructure.models.notification_delivery import (
    NotificationEmailDelivery as Delivery,
)
from infrastructure.models.notification_delivery import (
    NotificationEventReceipt as Receipt,
)
from infrastructure.models.users import User
from infrastructure.repositories import notification_email_repository as journal


@pytest_asyncio.fixture
async def mail_workflow(
    _engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[dict[str, Any]]:
    maker = async_sessionmaker(_engine, expire_on_commit=False)
    active = 0

    @asynccontextmanager
    async def tracked_session() -> AsyncIterator[AsyncSession]:
        nonlocal active
        active += 1
        try:
            async with maker() as session:
                yield session
        finally:
            active -= 1

    monkeypatch.setattr(email_delivery, "AsyncSessionLocal", tracked_session)
    async with maker() as session:
        company = Company(name="Notification SMTP test", company_type="other")
        user = User(
            phone=f"+7{str(uuid4().int)[:10]}",
            role="carcraft_employee",
            email="mail35@example.test",
            is_active=True,
        )
        session.add_all([company, user])
        await session.flush()
        application = LeasingApplication(
            company_id=company.id, created_by=user.id, display_number="TEST-35"
        )
        session.add(application)
        await session.flush()
        await session.commit()
    event_ids = []

    async def create(mode: str = "immediate") -> UUID:
        event = NotificationEvent.model_validate(
            {
                "event_id": uuid4(),
                "event_type": "leasing.application_status_changed",
                "entity_type": "leasing_application",
                "entity_id": application.id,
                "application_id": application.id,
                "aggregate_id": application.id,
                "request_number": "TEST-35",
                "occurred_at": datetime.now(UTC),
            }
        )
        event_ids.append(event.event_id)
        async with maker() as session:
            prefs = await session.get(EmailPreferences, user.id)
            if prefs is None:
                session.add(EmailPreferences(user_id=user.id, email_frequency=mode))
            else:
                prefs.email_frequency = mode
            await session.flush()
            ids = await process_notification_event(session, event)
            await session.commit()
        assert len(ids) == 1
        return ids[0]

    yield {
        "create": create,
        "maker": maker,
        "user_id": user.id,
        "active": lambda: active,
    }
    async with maker() as session:
        await session.execute(delete(Delivery).where(Delivery.user_id == user.id))
        await session.execute(delete(Batch).where(Batch.user_id == user.id))
        await session.execute(
            delete(Notification).where(Notification.user_id == user.id)
        )
        await session.execute(delete(Receipt).where(Receipt.event_id.in_(event_ids)))
        await session.execute(
            delete(LeasingApplication).where(LeasingApplication.id == application.id)
        )
        await session.execute(
            delete(EmailPreferences).where(EmailPreferences.user_id == user.id)
        )
        await session.execute(delete(User).where(User.id == user.id))
        await session.execute(delete(Company).where(Company.id == company.id))
        await session.commit()


async def test_unattempted_email_honors_changed_frequency(
    mail_workflow: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    workflow = mail_workflow
    delivery_id = await workflow["create"]()
    async with workflow["maker"]() as session:
        await session.execute(
            update(EmailPreferences)
            .where(EmailPreferences.user_id == workflow["user_id"])
            .values(email_frequency="daily")
        )
        await session.commit()
    sent = []

    async def smtp(*args: Any, **kwargs: Any) -> None:
        sent.append(args)

    monkeypatch.setattr(email_delivery, "send_email", smtp)
    await email_delivery.deliver_email(delivery_id)
    assert sent == []
    async with workflow["maker"]() as session:
        row = await session.get(Delivery, delivery_id)
        assert row.delivery_mode == "daily"
        assert row.status == "pending"
        assert row.next_attempt_at > datetime.now(UTC)


async def test_frequency_update_reschedules_future_weekly_intent_immediately(
    mail_workflow: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workflow = mail_workflow
    delivery_id = await workflow["create"]("weekly")
    async with workflow["maker"]() as session:
        await handle_update_email_preferences(
            UpdateEmailPreferencesCommand(
                workflow["user_id"], {"email_frequency": "immediate"}
            ),
            session,
        )
        await session.commit()
    sent = []

    async def smtp(*args: Any, **kwargs: Any) -> None:
        sent.append(kwargs["message_id"])

    monkeypatch.setattr(email_delivery, "send_email", smtp)
    assert await email_delivery.deliver_email(delivery_id) == "sent"
    assert len(sent) == 1


async def test_success_closes_session_before_smtp_and_replay_is_idle(
    mail_workflow: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    workflow = mail_workflow
    delivery_id = await workflow["create"]()
    messages = []

    async def smtp(to: str, subject: str, body: str, **kwargs: Any) -> None:
        assert workflow["active"]() == 0
        messages.append((to, subject, body, kwargs))

    monkeypatch.setattr(email_delivery, "send_email", smtp)
    assert await email_delivery.deliver_email(delivery_id) == "sent"
    assert await email_delivery.deliver_email(delivery_id) == "idle"
    assert len(messages) == 1
    assert messages[0][0] == "mail35@example.test"
    assert "/workspace/applications?application=" in messages[0][2]
    assert '<html lang="ru">' in messages[0][3]["html"]
    async with workflow["maker"]() as session:
        row = await session.get(Delivery, delivery_id)
        notification = await session.get(Notification, row.notification_id)
        assert row.attempt_count == 1 and row.sent_at is not None
        assert row.message_id == messages[0][3]["message_id"]
        assert notification.is_read is False


async def test_transient_smtp_error_retries_same_message_with_current_address(
    mail_workflow: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    workflow = mail_workflow
    delivery_id = await workflow["create"]()
    messages = []

    async def smtp(to: str, subject: str, body: str, **kwargs: Any) -> None:
        assert workflow["active"]() == 0
        messages.append((to, kwargs["message_id"]))
        if len(messages) == 1:
            raise smtplib.SMTPDataError(451, b"private secret mail35@example.test")

    monkeypatch.setattr(email_delivery, "send_email", smtp)
    assert await email_delivery.deliver_email(delivery_id) == "retry_wait"
    assert await email_delivery.deliver_email(delivery_id) == "idle"
    async with workflow["maker"]() as session:
        row = await session.get(Delivery, delivery_id)
        assert row.last_error == "SMTPDataError:451"
        assert row.attempt_count == 1 and row.failed_at is None
        await session.execute(
            update(Batch)
            .where(Batch.id == row.batch_id)
            .values(next_attempt_at=datetime.now(UTC) - timedelta(seconds=1))
        )
        await session.execute(
            update(User)
            .where(User.id == workflow["user_id"])
            .values(email="changed35@example.test")
        )
        await session.commit()
    assert await email_delivery.deliver_email(delivery_id) == "sent"
    assert messages[0][1] == messages[1][1]
    assert messages[1][0] == "changed35@example.test"


@pytest.mark.parametrize(("code", "expected"), [(550, "failed"), (451, "retry_wait")])
async def test_smtp_failures_preserve_inbox(
    mail_workflow: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    code: int,
    expected: str,
) -> None:
    workflow = mail_workflow
    delivery_id = await workflow["create"]()

    async def smtp(*args: Any, **kwargs: Any) -> None:
        raise smtplib.SMTPDataError(code, b"do not expose the provider response")

    monkeypatch.setattr(email_delivery, "send_email", smtp)
    assert await email_delivery.deliver_email(delivery_id) == expected
    async with workflow["maker"]() as session:
        row = await session.get(Delivery, delivery_id)
        assert row.status == expected
        assert (row.failed_at is not None) == (expected == "failed")
        assert "provider response" not in row.last_error
        assert await session.get(Notification, row.notification_id) is not None


@pytest.mark.parametrize(
    ("change", "state"),
    [
        ("inactive", "skipped_access_revoked"),
        ("preference", "skipped_preference"),
        ("email", "skipped_no_email"),
    ],
)
async def test_current_user_and_preference_are_rechecked(
    mail_workflow: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    change: str,
    state: str,
) -> None:
    workflow = mail_workflow
    delivery_id = await workflow["create"]()
    async with workflow["maker"]() as session:
        if change == "inactive":
            await session.execute(
                update(User)
                .where(User.id == workflow["user_id"])
                .values(is_active=False)
            )
        elif change == "email":
            await session.execute(
                update(User).where(User.id == workflow["user_id"]).values(email=None)
            )
        else:
            await session.execute(
                update(EmailPreferences)
                .where(EmailPreferences.user_id == workflow["user_id"])
                .values(application_status_emails=False)
            )
        await session.commit()

    async def smtp(*args: Any, **kwargs: Any) -> None:
        pytest.fail("Skipped delivery reached SMTP")

    monkeypatch.setattr(email_delivery, "send_email", smtp)
    assert await email_delivery.deliver_email(delivery_id) == "skipped"
    async with workflow["maker"]() as session:
        row = await session.get(Delivery, delivery_id)
        assert row.status == state and row.attempt_count == 0


async def test_concurrent_workers_do_not_send_twice(
    mail_workflow: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    workflow = mail_workflow
    delivery_id = await workflow["create"]()
    sending, release = asyncio.Event(), asyncio.Event()
    messages = []

    async def smtp(*args: Any, **kwargs: Any) -> None:
        assert workflow["active"]() == 0
        messages.append(kwargs["message_id"])
        sending.set()
        await asyncio.wait_for(release.wait(), 5)

    monkeypatch.setattr(email_delivery, "send_email", smtp)
    first = asyncio.create_task(email_delivery.deliver_email(delivery_id))
    try:
        await asyncio.wait_for(sending.wait(), 5)
        assert await email_delivery.deliver_email(delivery_id) == "idle"
    finally:
        release.set()
    assert await first == "sent"
    assert len(messages) == 1


async def test_digest_retry_keeps_original_membership_and_message_id(
    mail_workflow: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    workflow = mail_workflow
    ids = [await workflow["create"]("daily"), await workflow["create"]("daily")]
    async with workflow["maker"]() as session:
        await session.execute(
            update(Delivery)
            .where(Delivery.id.in_(ids))
            .values(next_attempt_at=datetime.now(UTC) - timedelta(seconds=1))
        )
        await session.commit()
    messages = []

    async def smtp(to: str, subject: str, body: str, **kwargs: Any) -> None:
        messages.append((body, kwargs["message_id"]))
        if len(messages) == 1:
            raise smtplib.SMTPDataError(451, b"temporary")

    monkeypatch.setattr(email_delivery, "send_email", smtp)
    assert await email_delivery.deliver_email(ids[0]) == "retry_wait"
    third = await workflow["create"]("daily")
    async with workflow["maker"]() as session:
        first = await session.get(Delivery, ids[0])
        second = await session.get(Delivery, ids[1])
        assert first.batch_id == second.batch_id
        await session.execute(
            update(Batch)
            .where(Batch.id == first.batch_id)
            .values(next_attempt_at=datetime.now(UTC) - timedelta(seconds=1))
        )
        await session.execute(
            update(Delivery)
            .where(Delivery.id == third)
            .values(next_attempt_at=datetime.now(UTC) - timedelta(seconds=1))
        )
        await session.commit()
    assert await email_delivery.deliver_email(ids[0]) == "sent"
    assert messages[0] == messages[1]
    assert messages[1][0].count("Открыть заявку:") == 2
    async with workflow["maker"]() as session:
        row = await session.get(Delivery, third)
        assert row.batch_id is None and row.status == "pending"


async def test_stale_worker_cannot_complete_reclaimed_batch(
    mail_workflow: dict[str, Any],
) -> None:
    workflow = mail_workflow
    delivery_id = await workflow["create"]()
    now = datetime.now(UTC)
    async with workflow["maker"]() as session:
        first = await journal.claim_batch(
            session,
            now=now,
            lease_seconds=600,
            limit=10,
            message_domain="example.test",
            delivery_id=delivery_id,
        )
        await session.commit()
    async with workflow["maker"]() as session:
        second = await journal.claim_batch(
            session,
            now=now + timedelta(seconds=601),
            lease_seconds=600,
            limit=10,
            message_domain="example.test",
            delivery_id=delivery_id,
        )
        await session.commit()
    assert first is not None and second is not None
    assert first["id"] == second["id"] and first["lease_token"] != second["lease_token"]
    async with workflow["maker"]() as session:
        assert (
            await journal.complete_batch(
                session, first["id"], first["lease_token"], status="sent", now=now
            )
            is False
        )
        assert (
            await journal.complete_batch(
                session, second["id"], second["lease_token"], status="sent", now=now
            )
            is True
        )
        await session.commit()


def test_retry_budget_is_six_total_attempts() -> None:
    now = datetime.now(UTC)
    exc = smtplib.SMTPDataError(451, b"temporary")
    assert email_delivery.failure_policy(exc, 1, now)[:2] == (
        "retry_wait",
        now + timedelta(seconds=60),
    )
    assert email_delivery.failure_policy(exc, 5, now)[:2] == (
        "retry_wait",
        now + timedelta(seconds=21600),
    )
    assert email_delivery.failure_policy(exc, 6, now)[:2] == ("failed", None)
