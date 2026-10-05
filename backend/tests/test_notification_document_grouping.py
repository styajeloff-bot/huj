"""Requested-document notifications at the consumer and durable repository seams."""

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from application.notifications import email_delivery
from application.notifications.document_grouping import finalize_document_upload_groups
from application.notifications.processor import process_notification_event
from domain.events.notifications import NotificationEvent
from infrastructure.models.applications import (
    LeasingApplication,
    LeasingCompanyApplication,
)
from infrastructure.models.companies import Company, LeasingCompany
from infrastructure.models.documents import (
    ApplicationDocument,
    ApplicationDocumentRequest,
    Document,
)
from infrastructure.models.email_preferences import EmailPreferences
from infrastructure.models.misc import Notification
from infrastructure.models.notification_delivery import (
    NotificationDocumentUploadGroup,
    NotificationDocumentUploadMember,
    NotificationEmailBatch,
    NotificationEmailDelivery,
    NotificationEventOutbox,
    NotificationEventReceipt,
)
from infrastructure.models.users import User
from infrastructure.repositories import notification_repository as inbox

FIRST_UPLOAD = datetime(2026, 9, 10, 9, 0, tzinfo=UTC)


@pytest_asyncio.fixture
async def document_graph(db_session: AsyncSession) -> dict[str, Any]:
    return await seed_document_graph(db_session)


async def seed_document_graph(db_session: AsyncSession) -> dict[str, Any]:
    buyer = Company(name="Grouping buyer", company_type="other", is_active=True)
    company = Company(
        name="Grouping LC", company_type="leasing_company", is_active=True
    )
    db_session.add_all([buyer, company])
    await db_session.flush()
    users = [
        User(
            name=f"LC {index}",
            phone=f"+7{uuid4().int % 10**16:016d}",
            email=f"grouping-{index}@test.local",
            role="leasing_company",
            company_id=company.id,
            is_active=True,
        )
        for index in range(2)
    ]
    lc = LeasingCompany(company_id=company.id, is_active=True)
    app = LeasingApplication(
        company_id=buyer.id, status="active", display_number="GROUP-35"
    )
    db_session.add_all([*users, lc, app])
    await db_session.flush()
    db_session.add(
        LeasingCompanyApplication(
            application_id=app.id, leasing_company_id=lc.id, status="documents_required"
        )
    )
    await db_session.flush()
    return {
        "buyer": buyer,
        "company": company,
        "lc": lc,
        "app": app,
        "users": users,
        "batch_id": uuid4(),
    }


async def upload_fact(
    session: AsyncSession,
    graph: dict[str, Any],
    *,
    at: datetime = FIRST_UPLOAD,
    batch_id: UUID | None = None,
) -> NotificationEvent:
    request = ApplicationDocumentRequest(
        application_id=graph["app"].id,
        leasing_company_id=graph["lc"].id,
        request_batch_id=batch_id or graph["batch_id"],
        document_type=str(uuid4()),
        display_name="Запрошенный документ",
        status="provided",
    )
    document = Document(
        company_id=graph["buyer"].id,
        document_type=request.document_type,
        related_application_id=graph["app"].id,
        file_name="requested.pdf",
    )
    session.add_all([request, document])
    await session.flush()
    session.add(
        ApplicationDocument(
            application_id=graph["app"].id,
            document_id=document.id,
            leasing_company_id=graph["lc"].id,
            document_request_id=request.id,
        )
    )
    await session.flush()
    return NotificationEvent(
        event_id=uuid4(),
        event_type="leasing.documents_uploaded",
        entity_type="leasing_application",
        entity_id=graph["app"].id,
        aggregate_id=graph["app"].id,
        application_id=graph["app"].id,
        request_number="GROUP-35",
        occurred_at=at,
        payload={
            "leasing_company_id": str(graph["lc"].id),
            "request_batch_id": str(request.request_batch_id),
            "document_request_id": str(request.id),
            "document_id": str(document.id),
        },
    )


@pytest.mark.asyncio
async def test_requested_upload_waits_for_group_without_losing_source_fact(
    db_session: AsyncSession,
    document_graph: dict[str, Any],
) -> None:
    event = await upload_fact(db_session, document_graph)
    assert await process_notification_event(db_session, event) == []
    assert (
        await db_session.scalar(sa.select(sa.func.count()).select_from(Notification))
        == 0
    )
    receipt = await db_session.get(NotificationEventReceipt, event.event_id)
    assert (
        receipt is not None
        and receipt.payload["payload"]["document_id"] == event.payload["document_id"]
    )


@pytest.mark.asyncio
async def test_ten_documents_close_once_at_ten_minutes_then_fan_out_one_summary_each(
    db_session: AsyncSession,
    document_graph: dict[str, Any],
) -> None:
    events = []
    for index in range(10):
        event = await upload_fact(
            db_session, document_graph, at=FIRST_UPLOAD + timedelta(seconds=index * 60)
        )
        events.append(event)
        assert await process_notification_event(db_session, event) == []
    assert await process_notification_event(db_session, events[0]) == []
    assert (
        await finalize_document_upload_groups(
            db_session, FIRST_UPLOAD + timedelta(minutes=9, seconds=59)
        )
        == 0
    )
    assert (
        await db_session.scalar(
            sa.select(sa.func.count()).select_from(NotificationEventOutbox)
        )
        == 0
    )
    assert (
        await finalize_document_upload_groups(
            db_session, FIRST_UPLOAD + timedelta(minutes=10)
        )
        == 1
    )
    assert (
        await finalize_document_upload_groups(
            db_session, FIRST_UPLOAD + timedelta(minutes=20)
        )
        == 0
    )
    summary = NotificationEvent.model_validate(
        (await db_session.scalars(sa.select(NotificationEventOutbox))).one().payload
    )
    assert summary.event_type == "leasing.documents_uploads_summary"
    assert summary.payload["document_count"] == 10
    assert summary.payload["first_upload_at"] == FIRST_UPLOAD.isoformat()
    assert datetime.fromisoformat(
        summary.payload["last_upload_at"]
    ) == FIRST_UPLOAD + timedelta(minutes=9)
    assert len(await process_notification_event(db_session, summary)) == 2
    assert await process_notification_event(db_session, summary) == []
    notifications = (await db_session.scalars(sa.select(Notification))).all()
    assert len(notifications) == 2
    assert {row.user_id for row in notifications} == {
        user.id for user in document_graph["users"]
    }
    assert all(
        row.type == "document_status" and "10" in row.message for row in notifications
    )
    assert all(
        row.data is not None and row.data["document_count"] == 10
        for row in notifications
    )
    assert (
        await db_session.scalar(
            sa.select(sa.func.count()).select_from(NotificationEmailDelivery)
        )
        == 2
    )


@pytest.mark.asyncio
async def test_summary_cannot_materialize_without_its_closed_durable_group(
    db_session: AsyncSession,
    document_graph: dict[str, Any],
) -> None:
    event = await upload_fact(db_session, document_graph)
    group_id = uuid4()
    summary = NotificationEvent.model_validate(
        event.model_dump()
        | {
            "event_id": group_id,
            "event_type": "leasing.documents_uploads_summary",
            "occurred_at": FIRST_UPLOAD + timedelta(minutes=10),
            "occurrence_key": f"leasing.documents_uploads_summary:{group_id}",
            "payload": {
                "leasing_company_id": str(document_graph["lc"].id),
                "request_batch_id": str(document_graph["batch_id"]),
                "group_id": str(group_id),
                "document_count": 1,
                "first_upload_at": FIRST_UPLOAD.isoformat(),
                "last_upload_at": FIRST_UPLOAD.isoformat(),
                "closes_at": (FIRST_UPLOAD + timedelta(minutes=10)).isoformat(),
            },
        }
    )
    assert await process_notification_event(db_session, summary) == []
    assert (
        await db_session.scalar(sa.select(sa.func.count()).select_from(Notification))
        == 0
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("order", [(599, 0, 1198), (599, 1198, 0), (1198, 599, 0)])
async def test_out_of_order_arrival_uses_first_actual_upload_not_arrival_time(
    db_session: AsyncSession,
    document_graph: dict[str, Any],
    order: tuple[int, ...],
) -> None:
    for seconds in order:
        event = await upload_fact(
            db_session, document_graph, at=FIRST_UPLOAD + timedelta(seconds=seconds)
        )
        await process_notification_event(db_session, event)
    assert (
        await finalize_document_upload_groups(
            db_session, FIRST_UPLOAD + timedelta(minutes=10)
        )
        == 1
    )
    summaries = (await db_session.scalars(sa.select(NotificationEventOutbox))).all()
    assert len(summaries) == 1
    assert summaries[0].payload["payload"]["document_count"] == 2
    assert (
        summaries[0].payload["payload"]["first_upload_at"] == FIRST_UPLOAD.isoformat()
    )
    pending = (
        await db_session.scalars(
            sa.select(NotificationDocumentUploadGroup).where(
                NotificationDocumentUploadGroup.closed_at.is_(None),
            )
        )
    ).one()
    assert pending.first_upload_at == FIRST_UPLOAD + timedelta(seconds=1198)


async def summary_events(session: AsyncSession) -> list[NotificationEvent]:
    return [
        NotificationEvent.model_validate(row.payload)
        for row in (
            await session.scalars(
                sa.select(NotificationEventOutbox)
                .where(
                    NotificationEventOutbox.event_type
                    == "leasing.documents_uploads_summary",
                )
                .order_by(NotificationEventOutbox.sequence)
            )
        ).all()
    ]


@pytest.mark.asyncio
async def test_boundary_upload_starts_next_window_without_debouncing_first(
    db_session: AsyncSession,
    document_graph: dict[str, Any],
) -> None:
    for seconds in (0, 599, 600):
        await process_notification_event(
            db_session,
            await upload_fact(
                db_session,
                document_graph,
                at=FIRST_UPLOAD + timedelta(seconds=seconds),
            ),
        )
    assert (
        await finalize_document_upload_groups(
            db_session, FIRST_UPLOAD + timedelta(minutes=10)
        )
        == 1
    )
    assert [
        item.payload["document_count"] for item in await summary_events(db_session)
    ] == [2]
    assert (
        await finalize_document_upload_groups(
            db_session, FIRST_UPLOAD + timedelta(minutes=19, seconds=59)
        )
        == 0
    )
    assert (
        await finalize_document_upload_groups(
            db_session, FIRST_UPLOAD + timedelta(minutes=20)
        )
        == 1
    )
    assert [
        item.payload["document_count"] for item in await summary_events(db_session)
    ] == [2, 1]


@pytest.mark.asyncio
@pytest.mark.parametrize("split", ["request_batch", "application", "leasing_company"])
async def test_different_request_scopes_never_mix(
    db_session: AsyncSession,
    document_graph: dict[str, Any],
    split: str,
) -> None:
    other = dict(document_graph)
    if split == "request_batch":
        other["batch_id"] = uuid4()
    elif split == "application":
        other["app"] = LeasingApplication(
            company_id=other["buyer"].id, display_number="GROUP-OTHER"
        )
        db_session.add(other["app"])
        await db_session.flush()
    else:
        company = Company(
            name="Other lender", company_type="leasing_company", is_active=True
        )
        db_session.add(company)
        await db_session.flush()
        other["lc"] = LeasingCompany(company_id=company.id, is_active=True)
        db_session.add(other["lc"])
        await db_session.flush()
    if split != "request_batch":
        db_session.add(
            LeasingCompanyApplication(
                application_id=other["app"].id, leasing_company_id=other["lc"].id
            )
        )
        await db_session.flush()
    for graph in (document_graph, other):
        await process_notification_event(
            db_session, await upload_fact(db_session, graph)
        )
    assert (
        await finalize_document_upload_groups(
            db_session, FIRST_UPLOAD + timedelta(minutes=10)
        )
        == 2
    )
    events = await summary_events(db_session)
    assert [event.payload["document_count"] for event in events] == [1, 1]
    assert (
        len(
            {
                (
                    event.application_id,
                    event.payload["leasing_company_id"],
                    event.payload["request_batch_id"],
                )
                for event in events
            }
        )
        == 2
    )


@pytest.mark.asyncio
async def test_duplicate_document_facts_are_audited_but_count_document_once(
    db_session: AsyncSession,
    document_graph: dict[str, Any],
) -> None:
    event = await upload_fact(db_session, document_graph)
    repeat = event.model_copy(update={"event_id": uuid4()})
    for fact in (event, repeat, event):
        await process_notification_event(db_session, fact)
    assert (
        await db_session.scalar(
            sa.select(sa.func.count()).select_from(NotificationDocumentUploadMember)
        )
        == 2
    )
    await finalize_document_upload_groups(
        db_session, FIRST_UPLOAD + timedelta(minutes=10)
    )
    assert (await summary_events(db_session))[0].payload["document_count"] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("legacy", ["no_batch", "no_request", "missing_request"])
async def test_old_payload_resolves_request_batch_or_keeps_individual_notification(
    db_session: AsyncSession,
    document_graph: dict[str, Any],
    legacy: str,
) -> None:
    event = await upload_fact(db_session, document_graph)
    payload = dict(event.payload)
    payload.pop("request_batch_id")
    if legacy == "no_request":
        payload.pop("document_request_id")
    elif legacy == "missing_request":
        payload["document_request_id"] = str(uuid4())
    event = event.model_copy(update={"payload": payload})
    result = await process_notification_event(db_session, event)
    assert len(result) == (0 if legacy == "no_batch" else 2)
    assert await finalize_document_upload_groups(
        db_session, FIRST_UPLOAD + timedelta(minutes=10)
    ) == (1 if legacy == "no_batch" else 0)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "corruption", ["request_batch_id", "document_id", "leasing_company_id"]
)
async def test_conflicting_request_identity_neither_groups_nor_notifies(
    db_session: AsyncSession,
    document_graph: dict[str, Any],
    corruption: str,
) -> None:
    event = await upload_fact(db_session, document_graph)
    event = event.model_copy(
        update={"payload": event.payload | {corruption: str(uuid4())}}
    )
    assert await process_notification_event(db_session, event) == []
    assert (
        await finalize_document_upload_groups(
            db_session, FIRST_UPLOAD + timedelta(minutes=10)
        )
        == 0
    )
    assert (
        await db_session.scalar(sa.select(sa.func.count()).select_from(Notification))
        == 0
    )


@pytest.mark.asyncio
async def test_late_upload_does_not_change_closed_summary_or_add_a_fresh_delay(
    db_session: AsyncSession,
    document_graph: dict[str, Any],
) -> None:
    await process_notification_event(
        db_session, await upload_fact(db_session, document_graph)
    )
    await finalize_document_upload_groups(
        db_session, FIRST_UPLOAD + timedelta(minutes=10)
    )
    original = (await summary_events(db_session))[0]
    await process_notification_event(db_session, original)
    rows = (await db_session.scalars(sa.select(Notification))).all()
    await inbox.mark_as_read(db_session, rows[0].id)
    await inbox.delete_by_id(db_session, rows[1].id)
    delayed = await upload_fact(
        db_session, document_graph, at=FIRST_UPLOAD + timedelta(minutes=2)
    )
    await process_notification_event(db_session, delayed)
    assert (
        await finalize_document_upload_groups(
            db_session, FIRST_UPLOAD + timedelta(minutes=20)
        )
        == 1
    )
    summaries = await summary_events(db_session)
    assert summaries[0] == original
    assert [item.payload["document_count"] for item in summaries] == [1, 1]
    assert summaries[1].occurred_at == FIRST_UPLOAD + timedelta(minutes=12)
    assert await process_notification_event(db_session, original) == []
    await db_session.refresh(rows[0])
    await db_session.refresh(rows[1])
    assert rows[0].is_read is True and rows[1].deleted_at is not None


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["receipt", "summary"])
async def test_crash_rolls_back_atomic_work_and_retry_recovers(
    db_session: AsyncSession,
    document_graph: dict[str, Any],
    stage: str,
) -> None:
    event = await upload_fact(db_session, document_graph)
    if stage == "summary":
        await process_notification_event(db_session, event)
    with pytest.raises(RuntimeError, match="simulated crash"):
        async with db_session.begin_nested():
            if stage == "receipt":
                await process_notification_event(db_session, event)
            else:
                await finalize_document_upload_groups(
                    db_session, FIRST_UPLOAD + timedelta(minutes=10)
                )
            raise RuntimeError("simulated crash before commit")
    if stage == "receipt":
        assert await db_session.get(NotificationEventReceipt, event.event_id) is None
        await process_notification_event(db_session, event)
    assert await summary_events(db_session) == []
    assert (
        await finalize_document_upload_groups(
            db_session, FIRST_UPLOAD + timedelta(minutes=10)
        )
        == 1
    )
    assert (await summary_events(db_session))[0].payload["document_count"] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mode,enabled",
    [("immediate", True), ("daily", True), ("weekly", True), ("immediate", False)],
)
async def test_summary_uses_current_recipients_and_document_email_preferences(
    db_session: AsyncSession,
    document_graph: dict[str, Any],
    mode: str,
    enabled: bool,
) -> None:
    await process_notification_event(
        db_session, await upload_fact(db_session, document_graph)
    )
    # Membership can change while the group is waiting; Kafka never freezes a
    # recipient list. The remaining member keeps inbox even with email disabled.
    document_graph["users"][1].is_active = False
    user = document_graph["users"][0]
    db_session.add(
        EmailPreferences(
            user_id=user.id, email_frequency=mode, document_status_emails=enabled
        )
    )
    await db_session.flush()
    await finalize_document_upload_groups(
        db_session, FIRST_UPLOAD + timedelta(minutes=10)
    )
    summary = (await summary_events(db_session))[0]
    before = datetime.now(UTC)
    assert len(await process_notification_event(db_session, summary)) == 1
    row = (await db_session.scalars(sa.select(Notification))).one()
    assert row.user_id == user.id and not row.is_read
    delivery = (await db_session.scalars(sa.select(NotificationEmailDelivery))).one()
    assert delivery.delivery_mode == mode
    assert delivery.status == ("pending" if enabled else "skipped_preference")
    assert delivery.next_attempt_at > before
    if mode != "immediate":
        assert delivery.next_attempt_at > datetime.now(UTC)


@pytest_asyncio.fixture
async def committed_document_graph(
    _engine: AsyncEngine,
) -> AsyncIterator[dict[str, Any]]:
    """Separate real transactions exercise advisory locks and restart recovery."""
    maker = async_sessionmaker(_engine, expire_on_commit=False)
    async with maker() as session:
        graph = await seed_document_graph(session)
        await session.commit()
    yield graph | {"maker": maker}
    # Remove only this fixture's synthetic graph, never another test's rows.
    app_id = graph["app"].id
    user_ids = [user.id for user in graph["users"]]
    async with maker() as session:
        for model in (NotificationEmailDelivery, NotificationEmailBatch, Notification):
            await session.execute(sa.delete(model).where(model.user_id.in_(user_ids)))
        group_ids = sa.select(NotificationDocumentUploadGroup.id).where(
            NotificationDocumentUploadGroup.application_id == app_id,
        )
        await session.execute(
            sa.delete(NotificationDocumentUploadMember).where(
                NotificationDocumentUploadMember.group_id.in_(group_ids),
            )
        )
        await session.execute(
            sa.delete(NotificationDocumentUploadGroup).where(
                NotificationDocumentUploadGroup.application_id == app_id,
            )
        )
        await session.execute(
            sa.delete(NotificationEventReceipt).where(
                NotificationEventReceipt.payload["aggregate_id"].astext == str(app_id),
            )
        )
        await session.execute(
            sa.delete(NotificationEventOutbox).where(
                NotificationEventOutbox.aggregate_id == app_id
            )
        )
        for application_model in (
            ApplicationDocument,
            ApplicationDocumentRequest,
            LeasingCompanyApplication,
        ):
            await session.execute(
                sa.delete(application_model).where(
                    application_model.application_id == app_id
                )
            )
        await session.execute(
            sa.delete(Document).where(Document.related_application_id == app_id)
        )
        await session.execute(
            sa.delete(LeasingApplication).where(LeasingApplication.id == app_id)
        )
        await session.execute(
            sa.delete(EmailPreferences).where(EmailPreferences.user_id.in_(user_ids))
        )
        await session.execute(sa.delete(User).where(User.id.in_(user_ids)))
        await session.execute(
            sa.delete(LeasingCompany).where(LeasingCompany.id == graph["lc"].id)
        )
        await session.execute(
            sa.delete(Company).where(
                Company.id.in_([graph["buyer"].id, graph["company"].id])
            )
        )
        await session.commit()


@pytest.mark.asyncio
async def test_competing_consumers_and_finalizers_commit_exactly_one_summary(
    committed_document_graph: dict[str, Any],
) -> None:
    graph = committed_document_graph
    maker = graph["maker"]
    async with maker() as session:
        events = [
            await upload_fact(
                session, graph, at=FIRST_UPLOAD + timedelta(seconds=seconds)
            )
            for seconds in (599, 0)
        ]
        await session.commit()

    async def consume(event: NotificationEvent) -> list[UUID]:
        async with maker() as session:
            result = await process_notification_event(session, event)
            await session.commit()
            return result

    async def close() -> int:
        async with maker() as session:
            result = await finalize_document_upload_groups(
                session, FIRST_UPLOAD + timedelta(minutes=10)
            )
            await session.commit()
            return result

    assert await asyncio.gather(
        consume(events[0]), consume(events[1]), consume(events[0])
    ) == [[], [], []]
    assert sum(await asyncio.gather(close(), close())) == 1
    async with maker() as session:
        summary = (await summary_events(session))[0]
        assert summary.payload["document_count"] == 2
    # New sessions mimic restart; simultaneous Kafka redelivery retains only
    # one personal inbox/delivery pair per authorized member.
    results = await asyncio.gather(consume(summary), consume(summary))
    assert sorted(map(len, results)) == [0, 2]
    async with maker() as session:
        assert (
            await session.scalar(
                sa.select(sa.func.count()).select_from(NotificationDocumentUploadMember)
            )
            == 2
        )
        assert (
            await session.scalar(sa.select(sa.func.count()).select_from(Notification))
            == 2
        )


@pytest.mark.asyncio
async def test_upload_waiting_on_closing_transaction_enters_next_durable_batch(
    committed_document_graph: dict[str, Any],
) -> None:
    graph = committed_document_graph
    maker = graph["maker"]
    async with maker() as session:
        first = await upload_fact(session, graph)
        late = await upload_fact(session, graph, at=FIRST_UPLOAD + timedelta(minutes=1))
        await process_notification_event(session, first)
        await session.commit()

    async def consume_late() -> None:
        async with maker() as session:
            await process_notification_event(session, late)
            await session.commit()

    task: asyncio.Task[None] | None = None
    try:
        async with maker() as closing_session:
            assert (
                await finalize_document_upload_groups(
                    closing_session, FIRST_UPLOAD + timedelta(minutes=10)
                )
                == 1
            )
            task = asyncio.create_task(consume_late())
            with pytest.raises(TimeoutError):
                await asyncio.wait_for(asyncio.shield(task), timeout=0.1)
            await closing_session.commit()
        await asyncio.wait_for(task, timeout=5)
    finally:
        if task is not None and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
    async with maker() as session:
        assert (
            await finalize_document_upload_groups(
                session, FIRST_UPLOAD + timedelta(minutes=20)
            )
            == 1
        )
        assert [
            event.payload["document_count"] for event in await summary_events(session)
        ] == [1, 1]
        await session.commit()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change", ["access", "preference", "daily", "weekly", "smtp_retry"]
)
async def test_summary_email_rechecks_changes_and_retries_through_existing_journal(
    committed_document_graph: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    change: str,
) -> None:
    graph = committed_document_graph
    maker = graph["maker"]
    monkeypatch.setattr(email_delivery, "AsyncSessionLocal", maker)
    user_id = graph["users"][0].id
    async with maker() as session:
        await process_notification_event(session, await upload_fact(session, graph))
        await finalize_document_upload_groups(
            session, FIRST_UPLOAD + timedelta(minutes=10)
        )
        await process_notification_event(session, (await summary_events(session))[0])
        delivery_id = await session.scalar(
            sa.select(NotificationEmailDelivery.id).where(
                NotificationEmailDelivery.user_id == user_id,
            )
        )
        if change == "access":
            await session.execute(
                sa.update(User).where(User.id == user_id).values(is_active=False)
            )
        elif change in {"preference", "daily", "weekly"}:
            session.add(
                EmailPreferences(
                    user_id=user_id,
                    document_status_emails=change != "preference",
                    email_frequency=change
                    if change in {"daily", "weekly"}
                    else "immediate",
                )
            )
        await session.commit()
    sent: list[dict[str, Any]] = []

    async def smtp(*args: Any, **kwargs: Any) -> None:
        sent.append(kwargs)
        if change == "smtp_retry" and len(sent) == 1:
            raise ConnectionError("synthetic SMTP outage")

    monkeypatch.setattr(email_delivery, "send_email", smtp)
    await email_delivery.deliver_email(delivery_id)
    async with maker() as session:
        row = await session.get(NotificationEmailDelivery, delivery_id)
        if change in {"access", "preference"}:
            assert sent == []
            assert row.status == (
                "skipped_access_revoked" if change == "access" else "skipped_preference"
            )
        elif change in {"daily", "weekly"}:
            assert sent == [] and row.delivery_mode == change
            assert row.status == "pending" and row.next_attempt_at > datetime.now(UTC)
        else:
            assert row.status == "retry_wait"
            past = datetime.now(UTC) - timedelta(seconds=1)
            await session.execute(
                sa.update(NotificationEmailDelivery)
                .where(
                    NotificationEmailDelivery.id == delivery_id,
                )
                .values(next_attempt_at=past)
            )
            await session.execute(
                sa.update(NotificationEmailBatch)
                .where(
                    NotificationEmailBatch.id == row.batch_id,
                )
                .values(next_attempt_at=past)
            )
        await session.commit()
    if change == "smtp_retry":
        await email_delivery.deliver_email(delivery_id)
        await email_delivery.deliver_email(delivery_id)
        assert len(sent) == 2
        assert sent[0]["message_id"] == sent[1]["message_id"]
        async with maker() as session:
            assert (
                await session.get(NotificationEmailDelivery, delivery_id)
            ).status == "sent"
