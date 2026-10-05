
"""TЗ35 Exchange: same object policy, transactional facts and deadline recovery."""
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from application.commands.exchange.create_bid import CreateBidCommand, handle_create_bid
from application.commands.exchange.update_bid import UpdateBidCommand, handle_update_bid
from application.commands.exchange.withdraw_bid import (
    WithdrawBidCommand,
    handle_withdraw_bid,
)
from application.notifications.exchange_deadlines import scan_exchange_deadlines
from application.queries.exchange.get_request import GetRequestQuery, handle_get_request
from application.services.exchange_access import can_read_exchange_request
from infrastructure.models.companies import Company, DistributorDealerLink
from infrastructure.models.exchange import ExchangeRequest, ExchangeRequestWarehouse
from infrastructure.models.notification_delivery import NotificationEventOutbox
from infrastructure.models.users import User, UserCompany
from infrastructure.models.vehicles import Warehouse
from presentation.schemas.exchange import CreateExchangeRequestBody
from tests.legacy_compat import Vehicle

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def graph(db_session: AsyncSession) -> dict[str, Any]:
    lc = Company(name="LC35", company_type="leasing_company")
    dealer = Company(name="Dealer35", company_type="dealer")
    distributor = Company(name="Distributor35", company_type="distributor")
    vehicle = Vehicle(status="available", is_available=True, base_price=Decimal("1000000"))
    db_session.add_all([lc, dealer, distributor, vehicle])
    await db_session.flush()
    owner = User(phone="+73500000001", role="leasing_company", company_id=lc.id, is_active=True)
    colleague = User(phone="+73500000002", role="leasing_company", is_active=True)
    seller = User(phone="+73500000003", role="dealer", company_id=dealer.id, is_active=True)
    observer = User(phone="+73500000004", role="distributor", company_id=distributor.id, is_active=True)
    warehouse = Warehouse(company_id=dealer.id, dealer_id=dealer.id, address="35", brand="35")
    db_session.add_all([owner, colleague, seller, observer, warehouse])
    await db_session.flush()
    membership = UserCompany(user_id=colleague.id, company_id=lc.id, can_view_applications=True, can_create_applications=True)
    request = ExchangeRequest(lc_user_id=owner.id, lc_company_id=lc.id, vehicle_id=vehicle.id,
        quantity=2, expiration_at=datetime.now(UTC) + timedelta(hours=23), batch_number=35, batch_index=1)
    db_session.add_all([membership, request, DistributorDealerLink(distributor_company_id=distributor.id, dealer_company_id=dealer.id)])
    await db_session.flush()
    db_session.add(ExchangeRequestWarehouse(request_id=request.id, warehouse_id=warehouse.id, dealer_id=dealer.id))
    await db_session.flush()
    return {"request": request, "owner": owner, "colleague": colleague, "seller": seller,
            "observer": observer, "membership": membership, "lc": lc, "dealer": dealer, "distributor": distributor}


async def test_company_colleague_can_read_then_loses_access(db_session: AsyncSession, graph: dict[str, Any]) -> None:
    result = await handle_get_request(GetRequestQuery(graph["request"].id, graph["colleague"].id,
        company_id=graph["lc"].id), db_session)
    assert result["request"]["lc_company_id"] == graph["lc"].id
    graph["membership"].can_view_applications = False
    await db_session.flush()
    assert not await can_read_exchange_request(db_session, request_id=graph["request"].id,
        user_id=graph["colleague"].id, role="leasing_company", company_id=graph["lc"].id)


async def test_scanner_idempotent_deadline_change_and_expiry(db_session: AsyncSession, graph: dict[str, Any]) -> None:
    now = datetime.now(UTC)
    assert await scan_exchange_deadlines(db_session, now) == 1
    assert await scan_exchange_deadlines(db_session, now) == 0
    graph["request"].expiration_at = now + timedelta(minutes=40)
    await db_session.flush()
    assert await scan_exchange_deadlines(db_session, now) == 1
    assert await scan_exchange_deadlines(db_session, now + timedelta(hours=1)) == 1
    assert await scan_exchange_deadlines(db_session, now + timedelta(hours=1)) == 0
    events = (await db_session.execute(select(NotificationEventOutbox).order_by(NotificationEventOutbox.sequence))).scalars().all()
    assert [event.event_type for event in events] == ["exchange.deadline_24h", "exchange.deadline_1h", "exchange.request_finalized"]
    assert events[1].payload["payload"]["remaining_seconds"] == 2400


async def test_bid_create_update_withdraw_preserve_immutable_facts(db_session: AsyncSession, graph: dict[str, Any]) -> None:
    result = await handle_create_bid(CreateBidCommand(graph["request"].id, graph["seller"].id,
        Decimal("900000"), company_id=graph["dealer"].id), db_session)
    bid_id = result["bid"]["id"]
    await handle_update_bid(UpdateBidCommand(bid_id, graph["seller"].id,
        company_id=graph["dealer"].id, price=Decimal("880000")), db_session)
    await handle_withdraw_bid(WithdrawBidCommand(bid_id, graph["seller"].id, graph["dealer"].id), db_session)
    events = (await db_session.execute(select(NotificationEventOutbox).order_by(NotificationEventOutbox.sequence))).scalars().all()
    assert [event.event_type for event in events] == ["exchange.bid_created", "exchange.bid_updated", "exchange.bid_withdrawn"]
    assert events[1].payload["previous_values"]["price"] == "900000.00"
    assert events[1].payload["new_values"]["price"] == "880000.00"
    assert events[2].payload["payload"]["dealer_company_id"] == str(graph["dealer"].id)


async def test_distributor_access_requires_membership_and_link(db_session: AsyncSession, graph: dict[str, Any]) -> None:
    assert await can_read_exchange_request(db_session, request_id=graph["request"].id,
        user_id=graph["observer"].id, role="distributor", company_id=graph["distributor"].id)
    assert not await can_read_exchange_request(db_session, request_id=graph["request"].id,
        user_id=graph["observer"].id, role="distributor", company_id=uuid4())


async def test_api_rejects_naive_and_date_only_deadlines() -> None:
    from pydantic import ValidationError
    for value in ("2026-09-10", "2026-09-10T12:00:00"):
        with pytest.raises(ValidationError):
            CreateExchangeRequestBody(vehicle_id=uuid4(), expiration_at=value)
    body = CreateExchangeRequestBody(vehicle_id=uuid4(), expiration_at="2026-09-10T12:00:00+03:00")
    assert body.expiration_at is not None
    assert body.expiration_at.utcoffset() == timedelta(hours=3)


async def test_request_update_and_archive_emit_only_real_changes(db_session: AsyncSession, graph: dict[str, Any]) -> None:
    from application.commands.exchange.archive_request import (
        ArchiveExchangeRequestCommand,
        handle_archive_exchange_request,
    )
    from application.commands.exchange.update_exchange_request import (
        UpdateExchangeRequestCommand,
        handle_update_exchange_request,
    )
    request_id, user_id, company_id = graph["request"].id, graph["owner"].id, graph["lc"].id
    await handle_update_exchange_request(UpdateExchangeRequestCommand(request_id, user_id,
        company_id=company_id, quantity=2), db_session)
    assert (await db_session.execute(select(NotificationEventOutbox))).scalars().all() == []
    await handle_update_exchange_request(UpdateExchangeRequestCommand(request_id, user_id,
        company_id=company_id, quantity=3, expiration_at_set=True), db_session)
    await handle_archive_exchange_request(ArchiveExchangeRequestCommand(request_id, user_id, company_id=company_id), db_session)
    events = (await db_session.execute(select(NotificationEventOutbox).order_by(NotificationEventOutbox.sequence))).scalars().all()
    assert [event.event_type for event in events] == ["exchange.request_changed", "exchange.request_finalized"]
    assert events[0].payload["previous_values"]["quantity"] == 2
    assert events[0].payload["new_values"] == {"quantity": 3, "expiration_at": None}


async def test_approve_emits_finalization_selected_and_nonselected(db_session: AsyncSession, graph: dict[str, Any]) -> None:
    from application.commands.exchange.approve_bid import (
        ApproveBidCommand,
        handle_approve_bid,
    )
    result = await handle_create_bid(CreateBidCommand(graph["request"].id, graph["seller"].id,
        Decimal("900000"), company_id=graph["dealer"].id), db_session)
    await handle_approve_bid(ApproveBidCommand(result["bid"]["id"], graph["owner"].id,
        company_id=graph["lc"].id), db_session)
    events = (await db_session.execute(select(NotificationEventOutbox).order_by(NotificationEventOutbox.sequence))).scalars().all()
    exchange = [event for event in events if event.event_type.startswith("exchange.")]
    assert [event.event_type for event in exchange] == ["exchange.bid_created", "exchange.request_finalized", "exchange.bid_selected", "exchange.bid_not_selected"]
    assert exchange[2].payload["payload"]["selected_dealer_company_id"] == str(graph["dealer"].id)
    failures = [event for event in events if event.event_type == "monetization.capture_failed"]
    assert len(events) == 5 and len(failures) == 1
    assert failures[0].aggregate_id == graph["request"].id
    # This historical Exchange fixture has no canonical LeasingCompany row.
    assert "лизинговая компания" in failures[0].payload["payload"]["reason"]


async def test_publication_outbox_rolls_back_with_request(db_session: AsyncSession, graph: dict[str, Any]) -> None:
    from application.commands.exchange.create_exchange_request import (
        CreateExchangeRequestCommand,
        handle_create_exchange_request,
    )
    from infrastructure.repositories.exchange_request_repository import get_by_id
    request_id = None
    with pytest.raises(RuntimeError, match="business rollback"):
        async with db_session.begin_nested():
            result = await handle_create_exchange_request(CreateExchangeRequestCommand(
                graph["owner"].id, graph["request"].vehicle_id, company_id=graph["lc"].id,
            ), db_session)
            request_id = result["request"]["id"]
            event = (await db_session.execute(select(NotificationEventOutbox))).scalar_one()
            assert event.event_type == "exchange.request_published"
            assert event.aggregate_id == request_id
            raise RuntimeError("business rollback")
    assert await get_by_id(db_session, request_id) is None
    assert (await db_session.execute(select(NotificationEventOutbox))).scalars().all() == []


@pytest.mark.parametrize("operation", ["create", "update", "archive", "resubmit", "approve", "submit_cart"])
async def test_business_dwh_date_preserves_moscow_deadline(
    db_session: AsyncSession, graph: dict[str, Any], monkeypatch: pytest.MonkeyPatch, operation: str,
) -> None:
    from importlib import import_module

    from infrastructure.models.exchange import (
        ExchangeCartItem,
        ExchangeCartItemWarehouse,
    )
    from infrastructure.settings import settings
    monkeypatch.setattr(settings, "notification_business_timezone", "Europe/Moscow")
    expiry = datetime(2099, 9, 7, 21, 30, tzinfo=UTC)
    graph["request"].expiration_at = expiry
    await db_session.flush()
    captures: list[dict[str, Any]] = []
    module_name = {
        "create": "create_exchange_request", "update": "update_exchange_request", "archive": "archive_request",
        "resubmit": "resubmit_request", "approve": "approve_bid", "submit_cart": "submit_exchange_cart",
    }[operation]
    module = import_module(f"application.commands.exchange.{module_name}")
    monkeypatch.setattr(module, "emit_exchange_request_changed", captures.append)
    owner, company, request = graph["owner"].id, graph["lc"].id, graph["request"]
    if operation == "create":
        await module.handle_create_exchange_request(module.CreateExchangeRequestCommand(
            owner, request.vehicle_id, company_id=company, expiration_at=expiry,
        ), db_session)
    elif operation == "update":
        await module.handle_update_exchange_request(module.UpdateExchangeRequestCommand(
            request.id, owner, company_id=company, quantity=3,
        ), db_session)
    elif operation == "archive":
        await module.handle_archive_exchange_request(module.ArchiveExchangeRequestCommand(
            request.id, owner, company_id=company,
        ), db_session)
    elif operation == "resubmit":
        request.status = "archived"
        await db_session.flush()
        await module.handle_resubmit_exchange_request(module.ResubmitExchangeRequestCommand(
            request.id, owner, company_id=company,
        ), db_session)
    elif operation == "approve":
        created = await handle_create_bid(CreateBidCommand(request.id, graph["seller"].id,
            Decimal("100"), company_id=graph["dealer"].id), db_session)
        await module.handle_approve_bid(module.ApproveBidCommand(created["bid"]["id"], owner,
            company_id=company), db_session)
    else:
        item = ExchangeCartItem(user_id=owner, vehicle_id=request.vehicle_id, expiration_at=expiry)
        db_session.add(item)
        await db_session.flush()
        warehouse_id = await db_session.scalar(select(ExchangeRequestWarehouse.warehouse_id).where(
            ExchangeRequestWarehouse.request_id == request.id))
        db_session.add(ExchangeCartItemWarehouse(cart_item_id=item.id, warehouse_id=warehouse_id))
        await db_session.flush()
        await module.handle_submit_exchange_cart(module.SubmitExchangeCartCommand(owner, company_id=company), db_session)
    assert len(captures) == 1
    assert captures[0]["expiration_date"] == "2099-09-08"


async def test_discount_change_survives_processed_inbox_and_email(
    db_session: AsyncSession, graph: dict[str, Any],
) -> None:
    from application.commands.exchange.update_exchange_request import (
        UpdateExchangeRequestCommand,
        handle_update_exchange_request,
    )
    from application.notifications.processor import process_notification_event
    from application.notifications.templates import build_email
    from domain.events.notifications import NotificationEvent
    from infrastructure.models.misc import Notification
    graph["request"].discount_type = "percent"
    graph["request"].discount_value = Decimal("5.00")
    await db_session.flush()
    await handle_update_exchange_request(UpdateExchangeRequestCommand(
        graph["request"].id, graph["owner"].id, company_id=graph["lc"].id,
        discount_value=Decimal("7.50"),
    ), db_session)
    fact = (await db_session.execute(select(NotificationEventOutbox))).scalar_one()
    await process_notification_event(db_session, NotificationEvent.model_validate(fact.payload))
    inbox = (await db_session.execute(select(Notification).where(
        Notification.user_id == graph["seller"].id,
    ))).scalar_one()
    assert inbox.data is not None
    assert inbox.data["changed_fields"] == ["discount_value"]
    assert inbox.data["previous_values"] == {"discount_value": "5.00"}
    assert inbox.data["new_values"] == {"discount_value": "7.50"}
    message = build_email([{"title": inbox.title, "message": inbox.message,
        "data": inbox.data, "action_url": inbox.action_url}], public_url="https://example.test", timezone="Europe/Moscow")
    assert "Размер скидки: 5.00 → 7.50" in message["body"]
    assert "Размер скидки: 5.00 → 7.50" in message["html"]


async def test_withdraw_http_requires_dealer_role_and_keeps_lc_denial_nonmutating(
    db_session: AsyncSession, graph: dict[str, Any], client: AsyncClient,
) -> None:
    from infrastructure.auth import generate_tokens
    from infrastructure.repositories.exchange_bid_repository import get_by_id
    created = await handle_create_bid(CreateBidCommand(graph["request"].id, graph["seller"].id,
        Decimal("100"), company_id=graph["dealer"].id), db_session)
    bid_id = created["bid"]["id"]
    lc_token, _ = generate_tokens(graph["owner"].id, "leasing_company", graph["lc"].id)
    dealer_token, _ = generate_tokens(graph["seller"].id, "dealer", graph["dealer"].id)
    path = f"/api/v1/exchange/bids/{bid_id}"
    rejected = await client.delete(path, headers={"Authorization": f"Bearer {lc_token}"})
    assert rejected.status_code == 403
    assert await get_by_id(db_session, bid_id) is not None
    accepted = await client.delete(path, headers={"Authorization": f"Bearer {dealer_token}"})
    assert accepted.status_code == 204
    assert await get_by_id(db_session, bid_id) is None
