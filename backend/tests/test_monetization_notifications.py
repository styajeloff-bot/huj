"""Transactional monetization facts never notify clients or leak commission values."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest

# The outbox/inbox checks use the real PostgreSQL tables. Only external delivery
# remains uncalled: these event policies intentionally have no email channel.
import pytest_asyncio
import sqlalchemy as sa
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from application.commands.monetization import deals as deal_commands
from application.commands.monetization import requests as request_commands
from application.notifications.monetization import notify_capture_result
from application.notifications.processor import process_notification_event
from application.notifications.templates import build_inbox
from domain.events.notifications import NotificationEvent
from domain.notification_policy import targets_context
from infrastructure.models.applications import LeasingApplication
from infrastructure.models.companies import Company, LeasingCompany
from infrastructure.models.misc import Notification
from infrastructure.models.notification_delivery import (
    NotificationEmailDelivery,
    NotificationEventOutbox,
)
from infrastructure.models.support import DealerGroup, DealerGroupMember
from infrastructure.models.users import User, UserCompany
from infrastructure.repositories import monetization_repository as monetization_repo


def _event(kind: str, **changes: Any) -> NotificationEvent:
    entity_id = uuid4()
    values: dict[str, Any] = {
        "event_id": uuid4(),
        "event_type": f"monetization.{kind}",
        "entity_type": "monetization_deal",
        "entity_id": entity_id,
        "aggregate_id": entity_id,
        "request_number": "MON-22268",
        "occurred_at": datetime(2026, 9, 16, tzinfo=UTC),
        "payload": {"revision": 1},
    }
    values.update(changes)
    return NotificationEvent.model_validate(values)


def test_internal_deal_fact_has_scoped_link_and_no_commission_values() -> None:
    company_id = uuid4()
    event = _event(
        "deal_created", payload={"revision": 1, "private_commission": "1000000"}
    )
    recipient = {"user_id": uuid4(), "role": "dealer", "company_id": company_id}
    view = build_inbox(event, recipient)
    assert (
        view["action_url"]
        == f"/workspace/monetization?deal={event.entity_id}&notification_company_id={company_id}"
    )
    assert "private_commission" not in view["data"]
    assert "1000000" not in str(view)
    assert targets_context(event, {"role": "client"}, {}) is False


def test_negotiation_link_opens_inbox_before_a_leasing_company_application_exists() -> (
    None
):
    application_id, request_id = uuid4(), uuid4()
    event = _event(
        "condition_requested",
        entity_type="monetization_condition_request",
        entity_id=request_id,
        aggregate_id=request_id,
        application_id=application_id,
        payload={"application_id": str(application_id)},
    )
    view = build_inbox(event, {"user_id": uuid4(), "role": "leasing_company"})
    assert view["action_url"] == f"/workspace/monetization?application={application_id}"
    assert targets_context(event, {"role": "dealer"}, {}) is False


def test_confirmation_fact_requires_party_and_revision() -> None:
    with pytest.raises(ValidationError):
        _event("party_confirmed")
    event = _event(
        "party_confirmed", payload={"revision": 2, "confirmed_party": "dealer"}
    )
    assert targets_context(event, {"role": "carcraft_employee"}, {}) is True
    assert targets_context(event, {"role": "dealer"}, {}) is False


@pytest_asyncio.fixture
async def notification_graph(
    db_session: AsyncSession, request: pytest.FixtureRequest
) -> dict[str, Any]:
    from datetime import date
    from decimal import Decimal

    from domain.monetization.programs import calculate_program

    companies = {
        name: Company(id=uuid4(), name=name, company_type=kind)
        for name, kind in (
            ("dealer", "dealer"),
            ("leasing", "leasing_company"),
            ("distributor", "distributor"),
            ("outsider", "dealer"),
            ("buyer", "other"),
        )
    }
    db_session.add_all(companies.values())
    await db_session.flush()
    users = {
        name: User(
            id=uuid4(),
            phone=str(uuid4())[:20],
            name=name,
            email=f"{name}@example.invalid",
            role=role,
            company_id=companies[company].id if company else None,
        )
        for name, role, company in (
            ("dealer", "dealer", "dealer"),
            ("leasing", "leasing_company", "leasing"),
            ("distributor", "distributor", "distributor"),
            ("staff", "carcraft_employee", None),
            ("outsider", "dealer", "outsider"),
            ("client", "client", "dealer"),
        )
    }
    db_session.add_all(users.values())
    leasing = LeasingCompany(id=uuid4(), company_id=companies["leasing"].id)
    db_session.add(leasing)
    await db_session.flush()
    group = DealerGroup(
        id=uuid4(), name="Notification dealer group", created_by=users["staff"].id,
        distributor_company_id=companies["distributor"].id,
    )
    db_session.add(group)
    await db_session.flush()
    db_session.add(DealerGroupMember(
        dealer_group_id=group.id, created_by=users["staff"].id,
        dealer_company_id=companies["dealer"].id,
    ))
    application = LeasingApplication(
        id=uuid4(),
        company_id=companies["buyer"].id,
        dealer_company_id=companies["dealer"].id,
        display_number="NOTIFY-22268",
    )
    db_session.add(application)
    await db_session.flush()
    conditions = await monetization_repo.create_program(
        db_session,
        {
            "name": "Notification conditions",
            "leasing_company_id": leasing.id,
            "period_start": date(2026, 1, 1),
            "period_end": None,
            "status": "active",
            "sources": [
                {
                    "source_type": "exchange",
                    "expenses": [
                        {
                            "local_id": "e1",
                            "participant_type": "leasing",
                            "base_type": "none",
                            "calc_type": "amount",
                            "value": Decimal("1000"),
                            "vat_excluded": False,
                        }
                    ],
                    "incomes": [
                        {
                            "local_id": name,
                            "participant_type": name,
                            "base_type": "expense_amount",
                            "expense_ref": "e1",
                            "calc_type": "percent",
                            "value": value,
                            "vat_excluded": False,
                        }
                        for name, value in (
                            ("dealer", Decimal("40")),
                            ("distributor", Decimal("10")),
                        )
                        if name != "distributor" or getattr(request, "param", True)
                    ],
                }
            ],
        },
        users["staff"].id,
    )
    context = {
        "exchange_request_id": uuid4(),
        "source_type": "exchange",
        "application_number": "EX-NOTIFY-22268",
        "leasing_company_id": leasing.id,
        "dealer_company_id": companies["dealer"].id,
        "distributor_company_id": companies["distributor"].id,
        "base_amount": Decimal("1000000"),
        "occurred_at": datetime(2026, 9, 16, tzinfo=UTC),
        "vehicles": [],
        "supports": [],
    }
    deal = await monetization_repo.insert_deal(
        db_session, context, conditions, calculate_program(conditions, context)
    )
    actors = {}
    for name in ("dealer", "leasing", "distributor", "staff"):
        actors[name] = await monetization_repo.resolve_actor(
            db_session, users[name].id, str(users[name].role), users[name].company_id
        )
    return {
        "companies": companies,
        "users": users,
        "leasing": leasing,
        "application": application,
        "context": context,
        "deal": deal,
        "actors": actors,
    }


async def _facts(
    session: AsyncSession, event_type: str | None = None
) -> list[NotificationEvent]:
    stmt = sa.select(NotificationEventOutbox).where(
        NotificationEventOutbox.event_type.like("monetization.%")
    )
    if event_type:
        stmt = stmt.where(NotificationEventOutbox.event_type == event_type)
    return [
        NotificationEvent.model_validate(row.payload)
        for row in (
            await session.scalars(stmt.order_by(NotificationEventOutbox.sequence))
        ).all()
    ]


async def _inbox_users(session: AsyncSession, event: NotificationEvent) -> set[UUID]:
    return {
        item
        for item in (
            await session.scalars(
                sa.select(Notification.user_id).where(
                    Notification.event_id == event.event_id
                )
            )
        ).all()
        if item is not None
    }


async def test_created_fact_is_deduplicated_and_only_participants_get_inbox_without_email(
    db_session: AsyncSession,
    notification_graph: dict[str, Any],
) -> None:
    graph = notification_graph
    for _ in range(2):
        await notify_capture_result(
            db_session, graph["context"], {"deal": graph["deal"], "reason": None}
        )
    facts = await _facts(db_session)
    assert len(facts) == 1
    assert await process_notification_event(db_session, facts[0]) == []
    assert await process_notification_event(db_session, facts[0]) == []
    assert await _inbox_users(db_session, facts[0]) == {
        graph["users"][name].id for name in ("dealer", "leasing", "distributor")
    }
    assert (
        await db_session.scalar(
            sa.select(sa.func.count()).select_from(NotificationEmailDelivery)
        )
        == 0
    )
    inbox = (
        await db_session.scalars(
            sa.select(Notification).where(Notification.event_id == facts[0].event_id)
        )
    ).all()
    assert len(inbox) == 3
    assert all("notification_company_id=" in (item.action_url or "") for item in inbox)
    assert all("1000000" not in str(item.data) for item in inbox)


async def test_actual_confirmation_commands_notify_admin_then_paid_notifies_participants(
    db_session: AsyncSession,
    notification_graph: dict[str, Any],
) -> None:
    graph = notification_graph
    deal_id = graph["deal"]["id"]
    await deal_commands.confirm(db_session, deal_id, graph["actors"]["dealer"], 1)
    facts = await _facts(db_session, "monetization.party_confirmed")
    assert len(facts) == 1 and facts[0].payload["confirmed_party"] == "dealer"
    await process_notification_event(db_session, facts[0])
    assert await _inbox_users(db_session, facts[0]) == {graph["users"]["staff"].id}
    for name in ("leasing", "distributor", "staff"):
        await deal_commands.confirm(db_session, deal_id, graph["actors"][name], 1)
    paid = await _facts(db_session, "monetization.deal_paid")
    assert len(paid) == 1
    await process_notification_event(db_session, paid[0])
    assert await _inbox_users(db_session, paid[0]) == {
        graph["users"][name].id for name in ("dealer", "leasing", "distributor")
    }
    assert (
        await db_session.scalar(
            sa.select(sa.func.count()).select_from(NotificationEmailDelivery)
        )
        == 0
    )


async def test_failed_capture_notifies_only_staff_and_retries_do_not_duplicate_it(
    db_session: AsyncSession,
    notification_graph: dict[str, Any],
) -> None:
    graph = notification_graph
    result = {"deal": None, "reason": "Найдены условия с одинаковым приоритетом"}
    await notify_capture_result(db_session, graph["context"], result)
    await notify_capture_result(db_session, graph["context"], result)
    facts = await _facts(db_session)
    assert len(facts) == 1
    await process_notification_event(db_session, facts[0])
    assert await _inbox_users(db_session, facts[0]) == {graph["users"]["staff"].id}
    item = (
        await db_session.scalars(
            sa.select(Notification).where(Notification.event_id == facts[0].event_id)
        )
    ).one()
    assert result["reason"] is not None
    assert result["reason"] in (item.message or "")
    assert (
        item.action_url
        == f"/workspace/exchange?request={graph['context']['exchange_request_id']}"
    )


async def test_commission_commands_notify_each_counterparty_before_first_lca(
    db_session: AsyncSession,
    notification_graph: dict[str, Any],
) -> None:
    from decimal import Decimal

    graph = notification_graph
    created = await request_commands.create_requests(
        db_session,
        graph["application"].id,
        graph["actors"]["dealer"],
        {
            "leasing_company_ids": [graph["leasing"].id],
            "calc_type": "percent",
            "value": Decimal("1"),
        },
    )
    request_id = created["requests"][0]["id"]
    requested = (await _facts(db_session, "monetization.condition_requested"))[0]
    await process_notification_event(db_session, requested)
    assert await _inbox_users(db_session, requested) == {graph["users"]["leasing"].id}
    await request_commands.respond(
        db_session,
        request_id,
        graph["actors"]["leasing"],
        {
            "decision": "countered",
            "counter_calc_type": "percent",
            "counter_value": Decimal("2"),
        },
    )
    responded = (await _facts(db_session, "monetization.condition_responded"))[0]
    await process_notification_event(db_session, responded)
    assert await _inbox_users(db_session, responded) == {graph["users"]["dealer"].id}
    await request_commands.decide(
        db_session, request_id, graph["actors"]["dealer"], "accept_counter"
    )
    decided = (await _facts(db_session, "monetization.condition_decided"))[0]
    await process_notification_event(db_session, decided)
    assert await _inbox_users(db_session, decided) == {graph["users"]["leasing"].id}
    item = (
        await db_session.scalars(
            sa.select(Notification).where(Notification.event_id == requested.event_id)
        )
    ).one()
    assert (
        item.action_url
        == f"/workspace/monetization?application={graph['application'].id}&notification_company_id={graph['companies']['leasing'].id}"
    )
    assert "counter_value" not in str(item.data) and "requested_value" not in str(
        item.data
    )
    assert (
        await db_session.scalar(
            sa.select(sa.func.count()).select_from(NotificationEmailDelivery)
        )
        == 0
    )


async def test_revoked_company_membership_prevents_queued_notification_delivery(
    db_session: AsyncSession,
    notification_graph: dict[str, Any],
) -> None:
    graph = notification_graph
    await notify_capture_result(db_session, graph["context"], {"deal": graph["deal"]})
    db_session.add(
        UserCompany(
            user_id=graph["users"]["dealer"].id,
            company_id=graph["companies"]["dealer"].id,
            can_view_applications=False,
        )
    )
    await db_session.flush()
    event = (await _facts(db_session))[0]
    await process_notification_event(db_session, event)
    assert await _inbox_users(db_session, event) == {
        graph["users"][name].id for name in ("leasing", "distributor")
    }


async def test_event_rolls_back_with_callers_transaction(
    db_session: AsyncSession,
    notification_graph: dict[str, Any],
) -> None:
    graph = notification_graph
    with pytest.raises(RuntimeError, match="business rollback"):
        async with db_session.begin_nested():
            await notify_capture_result(
                db_session, graph["context"], {"deal": graph["deal"]}
            )
            raise RuntimeError("business rollback")
    assert await _facts(db_session) == []


@pytest.mark.parametrize("operation", ["confirmation", "request", "capture"])
async def test_enqueue_sql_failure_rolls_back_action_with_its_fact(
    db_session: AsyncSession,
    notification_graph: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
) -> None:
    from decimal import Decimal

    from sqlalchemy.exc import DBAPIError

    from infrastructure.repositories import notification_outbox_repository

    async def unavailable(
        session: AsyncSession, event: NotificationEvent
    ) -> UUID | None:
        await session.execute(sa.text("SELECT 1 / 0"))
        return None

    graph = notification_graph
    deal_id = graph["deal"]["id"]
    source = {**graph["context"], "exchange_request_id": uuid4()}
    application_id = graph["application"].id
    monkeypatch.setattr(notification_outbox_repository, "append_event", unavailable)
    with pytest.raises(DBAPIError):
        async with db_session.begin_nested():
            if operation == "confirmation":
                await deal_commands.confirm(db_session, deal_id, graph["actors"]["dealer"], 1)
            elif operation == "request":
                await request_commands.create_requests(
                    db_session, application_id, graph["actors"]["dealer"],
                    {"leasing_company_ids": [graph["leasing"].id],
                     "calc_type": "percent", "value": Decimal("1")},
                )
            else:
                await deal_commands.capture(db_session, source)
    stored = await monetization_repo.get_deal(db_session, deal_id)
    assert stored is not None and stored["revision"] == 1
    assert stored["status"] == "pending_approval" and stored["confirmations"] == {}
    assert await monetization_repo.find_source_deal(db_session, source) is None
    assert await monetization_repo.list_condition_requests(
        db_session, application_id, graph["actors"]["dealer"]
    ) == []
    assert await _facts(db_session) == []


def test_application_capture_failure_links_to_source_application() -> None:
    application_id = uuid4()
    event = _event(
        "capture_failed", entity_type="monetization_capture",
        application_id=application_id, payload={"reason": "Условия не найдены"},
    )
    view = build_inbox(event, {"user_id": uuid4(), "role": "carcraft_employee"})
    assert view["action_url"] == f"/workspace/applications?application={application_id}"
    assert "Условия не найдены" in view["message"]


@pytest.mark.parametrize("notification_graph", [False], indirect=True)
async def test_distributor_without_a_financial_row_does_not_receive_deal_notification(
    db_session: AsyncSession, notification_graph: dict[str, Any],
) -> None:
    graph = notification_graph
    await notify_capture_result(db_session, graph["context"], {"deal": graph["deal"]})
    event = (await _facts(db_session))[0]
    await process_notification_event(db_session, event)
    assert await _inbox_users(db_session, event) == {
        graph["users"][name].id for name in ("leasing", "dealer")
    }


async def test_removed_dealer_group_member_prevents_queued_distributor_notification(
    db_session: AsyncSession,
    notification_graph: dict[str, Any],
) -> None:
    graph = notification_graph
    await notify_capture_result(db_session, graph["context"], {"deal": graph["deal"]})
    await db_session.execute(
        sa.delete(DealerGroupMember).where(
            DealerGroupMember.dealer_company_id == graph["companies"]["dealer"].id
        )
    )
    event = (await _facts(db_session))[0]
    await process_notification_event(db_session, event)
    assert await _inbox_users(db_session, event) == {
        graph["users"][name].id for name in ("leasing", "dealer")
    }
