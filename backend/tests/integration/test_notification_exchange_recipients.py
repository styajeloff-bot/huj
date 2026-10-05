"""Every Exchange event fans out only to currently authorized participants."""
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from application.notifications.processor import process_notification_event
from domain.events.notifications import NotificationEvent
from infrastructure.models.companies import Company, DistributorDealerLink
from infrastructure.models.exchange import ExchangeBid, ExchangeRequestWarehouse
from infrastructure.models.misc import Notification
from infrastructure.models.users import User, UserCompany
from infrastructure.models.vehicles import Warehouse
from tests.integration.test_exchange_notification_flow import graph  # noqa: F401

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def audience(db_session: AsyncSession, graph: dict[str, Any]) -> dict[str, Any]:  # noqa: F811 -- imported pytest fixture
    company2 = Company(name="Second bidder", company_type="dealer")
    invited_company = Company(name="Invited without bid", company_type="dealer")
    other_distributor = Company(name="Other distributor", company_type="distributor")
    db_session.add_all([company2, invited_company, other_distributor])
    await db_session.flush()
    colleague_seller = User(phone="+73500000005", role="dealer", company_id=graph["dealer"].id, is_active=True)
    second_seller = User(phone="+73500000006", role="dealer", company_id=company2.id, is_active=True)
    invited = User(phone="+73500000007", role="dealer", company_id=invited_company.id, is_active=True)
    other_observer = User(phone="+73500000008", role="distributor", company_id=other_distributor.id, is_active=True)
    blocked = User(phone="+73500000009", role="dealer", company_id=graph["dealer"].id, is_active=True)
    inactive = User(phone="+73500000010", role="dealer", company_id=graph["dealer"].id, is_active=False)
    warehouse2 = Warehouse(company_id=company2.id, dealer_id=company2.id, address="Second", brand="35")
    warehouse3 = Warehouse(company_id=invited_company.id, dealer_id=invited_company.id, address="Invited", brand="35")
    db_session.add_all([colleague_seller, second_seller, invited, other_observer, blocked, inactive, warehouse2, warehouse3])
    await db_session.flush()
    request_id = graph["request"].id
    bid = ExchangeBid(request_id=request_id, dealer_id=graph["seller"].id,
        dealer_company_id=graph["dealer"].id, price=Decimal("100"), quantity=1)
    db_session.add_all([bid, ExchangeBid(request_id=request_id, dealer_id=second_seller.id,
        dealer_company_id=company2.id, price=Decimal("110"), quantity=1),
        ExchangeRequestWarehouse(request_id=request_id, warehouse_id=warehouse2.id, dealer_id=company2.id),
        ExchangeRequestWarehouse(request_id=request_id, warehouse_id=warehouse3.id, dealer_id=invited_company.id),
        DistributorDealerLink(distributor_company_id=other_distributor.id, dealer_company_id=company2.id),
        UserCompany(user_id=blocked.id, company_id=graph["dealer"].id, can_view_applications=False),
    ])
    await db_session.flush()
    return graph | {"colleague_seller": colleague_seller, "second_seller": second_seller,
                    "invited": invited, "other_observer": other_observer, "bid": bid,
                    "blocked": blocked, "inactive": inactive}


def event_for(audience: dict[str, Any], event_type: str) -> NotificationEvent:
    is_bid = event_type.startswith("exchange.bid_")
    payload = {"expiration_at": audience["request"].expiration_at.isoformat()}
    if is_bid:
        payload.update(dealer_company_id=str(audience["dealer"].id), selected_dealer_company_id=str(audience["dealer"].id))
    return NotificationEvent.model_validate({
        "event_id": uuid4(), "event_type": event_type,
        "entity_type": "exchange_bid" if is_bid else "exchange_request",
        "entity_id": audience["bid"].id if is_bid else audience["request"].id,
        "aggregate_id": audience["request"].id, "request_number": "35-1",
        "actor_user_id": audience["seller"].id if event_type in {
            "exchange.bid_created", "exchange.bid_updated", "exchange.bid_withdrawn",
        } else audience["owner"].id,
        "occurred_at": datetime.now(UTC),
        "payload": payload,
    })


DEALERS = {"seller", "colleague_seller", "second_seller", "invited"}
LC = {"owner", "colleague"}
DISTRIBUTORS = {"observer", "other_observer"}


@pytest.mark.parametrize(("event_type", "expected"), [
    ("exchange.request_published", DEALERS),
    ("exchange.bid_created", LC | {"observer", "second_seller", "invited"}),
    ("exchange.bid_updated", LC | {"observer", "second_seller", "invited"}),
    ("exchange.bid_withdrawn", LC | {"observer", "second_seller", "invited"}),
    ("exchange.request_changed", DEALERS | DISTRIBUTORS),
    ("exchange.deadline_24h", DEALERS),
    ("exchange.deadline_1h", DEALERS),
    ("exchange.request_finalized", DEALERS | LC | DISTRIBUTORS),
    ("exchange.bid_selected", {"seller", "colleague_seller"}),
    ("exchange.bid_not_selected", {"second_seller"}),
])
async def test_exchange_matrix_persists_only_correct_personal_inboxes(db_session: AsyncSession, audience: dict[str, Any], event_type: str, expected: set[str]) -> None:
    event = event_for(audience, event_type)
    deliveries = await process_notification_event(db_session, event)
    rows = (await db_session.execute(select(Notification).where(Notification.event_id == event.event_id))).scalars().all()
    assert {row.user_id for row in rows} == {audience[name].id for name in expected}
    assert len(deliveries) == len(expected)
    assert all(row.application_id is None for row in rows)
    assert all(row.data is not None and row.data["event_type"] == event_type for row in rows)
    assert audience["blocked"].id not in {row.user_id for row in rows}
    assert audience["inactive"].id not in {row.user_id for row in rows}
    assert await process_notification_event(db_session, event) == []


async def test_closed_or_changed_deadline_does_not_materialize_reminder(db_session: AsyncSession, audience: dict[str, Any]) -> None:
    event = event_for(audience, "exchange.deadline_1h")
    audience["request"].status = "archived"
    await db_session.flush()
    assert await process_notification_event(db_session, event) == []
    assert (await db_session.execute(select(Notification))).scalars().all() == []


async def test_distributor_http_is_readonly_and_projects_only_linked_dealers(client: AsyncClient, audience: dict[str, Any]) -> None:
    from infrastructure.auth import generate_tokens
    token, _ = generate_tokens(audience["observer"].id, "distributor", audience["distributor"].id)
    headers = {"Authorization": f"Bearer {token}"}
    path = "/api/v1/exchange/distributor/requests"
    response = await client.get(path, headers=headers)
    assert response.status_code == 200
    assert set(response.json()) == {"items", "pagination"}
    assert response.json()["pagination"]["total"] == 1
    request = response.json()["items"][0]
    assert {bid["id"] for bid in request["bids"]} == {str(audience["bid"].id)}
    assert {row["dealer_id"] for row in request["warehouses"]} == {str(audience["dealer"].id)}
    detail = await client.get(f'{path}/{audience["request"].id}', headers=headers)
    assert detail.status_code == 200
    assert len(detail.json()["request"]["bids"]) == 1
    counts = await client.get(path + "/counts", headers=headers)
    assert counts.status_code == 200
    assert counts.json()["counts"]["open"] == 1
    assert (await client.post(path, headers=headers, json={})).status_code == 405


async def test_dealer_competitor_projection_does_not_expose_private_fields(db_session: AsyncSession, audience: dict[str, Any]) -> None:
    event = event_for(audience, "exchange.bid_updated").model_copy(update={
        "previous_values": {"price": "100", "comment": "private original"},
        "new_values": {"price": "90", "comment": "private updated"},
        "changed_fields": ["price", "comment"],
    })
    await process_notification_event(db_session, event)
    row = (await db_session.execute(select(Notification).where(
        Notification.event_id == event.event_id, Notification.user_id == audience["second_seller"].id,
    ))).scalar_one()
    assert row.data is not None
    assert row.data["changed_fields"] == ["price"]
    assert row.data["previous_values"] == {"price": "100"}
    assert "private" not in str(row.data)
    assert str(audience["dealer"].id) not in str(row.data)


async def test_choose_bid_cascade_sends_one_notice_per_participant(db_session: AsyncSession, audience: dict[str, Any]) -> None:
    from collections import Counter

    from application.commands.exchange.approve_bid import (
        ApproveBidCommand,
        handle_approve_bid,
    )
    from infrastructure.models.notification_delivery import NotificationEventOutbox
    admin = User(phone="+73500000999", role="carcraft_employee", is_active=True)
    db_session.add(admin)
    await db_session.flush()
    await handle_approve_bid(ApproveBidCommand(audience["bid"].id, audience["owner"].id,
        company_id=audience["lc"].id), db_session)
    facts = (await db_session.execute(select(NotificationEventOutbox).order_by(NotificationEventOutbox.sequence))).scalars().all()
    assert {fact.event_type for fact in facts} == {"exchange.request_finalized", "exchange.bid_selected", "exchange.bid_not_selected", "monetization.capture_failed"}
    failure = next(fact for fact in facts if fact.event_type == "monetization.capture_failed")
    assert failure.aggregate_id == audience["request"].id
    for fact in facts:
        deliveries = await process_notification_event(db_session, NotificationEvent.model_validate(fact.payload))
        if fact.event_type == "monetization.capture_failed":
            assert deliveries == []
    rows = (await db_session.execute(select(Notification))).scalars().all()
    exchange_rows = [row for row in rows if row.event_id != failure.event_id]
    assert Counter(row.user_id for row in exchange_rows) == Counter({audience[name].id: 1 for name in DEALERS | LC | DISTRIBUTORS})
    failure_rows = [row for row in rows if row.event_id == failure.event_id]
    assert len(failure_rows) == 1 and failure_rows[0].user_id == admin.id
    assert failure_rows[0].action_url == f"/workspace/exchange?request={audience['request'].id}"


@pytest_asyncio.fixture(params=[
    ("seller", "dealer", "dealer", "requests/dealer"),
    ("owner", "lc", "leasing_company", "requests"),
    ("observer", "distributor", "distributor", "distributor/requests"),
])
async def secondary_company(
    request: pytest.FixtureRequest, db_session: AsyncSession, audience: dict[str, Any],
) -> dict[str, Any]:
    actor_name, company_name, role, resource = request.param
    actor, company = audience[actor_name], audience[company_name]
    primary = Company(name="Different primary company", company_type=role)
    db_session.add(primary)
    await db_session.flush()
    actor.company_id = primary.id
    membership = UserCompany(user_id=actor.id, company_id=company.id,
        can_view_applications=True, can_create_applications=True)
    db_session.add(membership)
    await db_session.flush()
    return {"actor": actor, "company": company, "role": role, "resource": resource,
        "primary": primary, "membership": membership}


async def test_notification_context_opens_secondary_company_and_rechecks_access(
    client: AsyncClient, db_session: AsyncSession, audience: dict[str, Any],
    secondary_company: dict[str, Any],
) -> None:
    from infrastructure.auth import generate_tokens

    actor, company = secondary_company["actor"], secondary_company["company"]
    role, resource = secondary_company["role"], secondary_company["resource"]
    primary, membership = secondary_company["primary"], secondary_company["membership"]
    event = event_for(audience, "exchange.request_finalized").model_copy(update={"actor_user_id": None})
    await process_notification_event(db_session, event)
    token, _ = generate_tokens(actor.id, role, primary.id)
    headers = {"Authorization": f"Bearer {token}"}
    inbox = await client.get("/api/v1/notifications", headers=headers)
    assert inbox.status_code == 200
    notice = next(row for row in inbox.json()["notifications"] if row["event_id"] == str(event.event_id))
    action = urlsplit(notice["action_url"])
    assert parse_qs(action.query) == {
        "request": [str(audience["request"].id)], "notification_company_id": [str(company.id)],
    }
    path = f'/api/v1/exchange/{resource}/{audience["request"].id}'
    assert (await client.get(path, headers=headers)).status_code == 403
    query = {"notification_company_id": str(company.id)}
    response = await client.get(path, headers=headers, params=query)
    assert response.status_code == 200, response.text
    assert response.json()["request"]["id"] == str(audience["request"].id)
    collection = f"/api/v1/exchange/{resource}"
    assert (await client.get(collection, headers=headers, params=query)).status_code == 200
    counts = await client.get(collection + "/counts", headers=headers, params=query)
    assert counts.status_code == 200
    assert counts.json()["counts"]["open"] == 1
    assert (await client.get(path, headers=headers, params={"notification_company_id": str(uuid4())})).status_code == 403
    write_path = path if role == "leasing_company" else f'/api/v1/exchange/bids/{audience["bid"].id}'
    body = {"quantity": 3} if role == "leasing_company" else {"price": "120"}
    membership.can_create_applications = False
    await db_session.flush()
    assert (await client.get(path, headers=headers, params=query)).status_code == 200
    denied = await client.put(write_path, headers=headers, params=query, json=body)
    assert denied.status_code == 403, denied.text
    membership.can_create_applications = True
    await db_session.flush()
    allowed = await client.put(write_path, headers=headers, params=query, json=body)
    assert allowed.status_code == (403 if role == "distributor" else 200), allowed.text
    membership.can_view_applications = False
    await db_session.flush()
    assert (await client.get(path, headers=headers, params=query)).status_code == 403
    membership.can_view_applications = True
    company.is_active = False
    await db_session.flush()
    assert (await client.get(path, headers=headers, params=query)).status_code == 403
    company.is_active = True
    await db_session.delete(membership)
    await db_session.flush()
    assert (await client.get(path, headers=headers, params=query)).status_code == 403
    assert actor.company_id == primary.id


@pytest.mark.parametrize("invalid_identity", ["inactive", "deleted", "changed_role"])
@pytest.mark.parametrize("explicit_context", [False, True])
async def test_exchange_company_context_rejects_stale_identity_even_without_selector(
    client: AsyncClient, db_session: AsyncSession, audience: dict[str, Any],
    invalid_identity: str, explicit_context: bool,
) -> None:
    from infrastructure.auth import generate_tokens

    actor = audience["seller"]
    token, _ = generate_tokens(actor.id, "dealer", actor.company_id)
    if invalid_identity == "inactive":
        actor.is_active = False
    elif invalid_identity == "deleted":
        actor.deleted_at = datetime.now(UTC)
    else:
        actor.role = "client"
    await db_session.flush()
    params = {"notification_company_id": str(actor.company_id)} if explicit_context else {}
    response = await client.get(f'/api/v1/exchange/requests/dealer/{audience["request"].id}',
        headers={"Authorization": f"Bearer {token}"}, params=params)
    assert response.status_code == 403


async def test_company_selector_returns_target_permissions_instead_of_primary_flags(
    db_session: AsyncSession, audience: dict[str, Any],
) -> None:
    from application.services.notification_company_context import (
        require_notification_company_context,
    )

    actor, company = audience["seller"], audience["dealer"]
    primary = Company(name="Primary with full permissions", company_type="dealer")
    db_session.add(primary)
    await db_session.flush()
    actor.company_id = primary.id
    membership = UserCompany(user_id=actor.id, company_id=company.id,
        sub_role="employee", can_view_applications=True, can_create_applications=False)
    db_session.add(membership)
    await db_session.flush()
    context = await require_notification_company_context(db_session,
        user_id=actor.id, role="dealer", company_id=primary.id, notification_company_id=company.id)
    assert context == {"company_id": company.id, "notification_company_id": company.id,
        "sub_role": "employee", "can_view_applications": True, "can_create_applications": False}
    membership.sub_role = "manager"
    membership.can_create_applications = True
    await db_session.flush()
    context = await require_notification_company_context(db_session,
        user_id=actor.id, role="dealer", company_id=primary.id, notification_company_id=company.id)
    assert context["sub_role"] == "manager"
    assert context["can_create_applications"] is True


async def test_no_selector_leaves_exchange_read_and_bid_write_guards_in_force(
    client: AsyncClient, db_session: AsyncSession, audience: dict[str, Any],
) -> None:
    from infrastructure.auth import generate_tokens

    actor, company = audience["seller"], audience["dealer"]
    db_session.add(UserCompany(user_id=actor.id, company_id=company.id,
        can_view_applications=False, can_create_applications=True))
    await db_session.flush()
    token, _ = generate_tokens(actor.id, "dealer", company.id)
    headers = {"Authorization": f"Bearer {token}"}
    detail = await client.get(f'/api/v1/exchange/requests/dealer/{audience["request"].id}', headers=headers)
    assert detail.status_code == 403
    bid = await client.put(f'/api/v1/exchange/bids/{audience["bid"].id}',
        headers=headers, json={"price": "120"})
    assert bid.status_code == 403


@pytest.mark.parametrize(("rename_file", "replace_file"), [(False, True), (True, True), (True, False)])
async def test_patch_attachment_materializes_safe_inbox_and_email_once(
    client: AsyncClient, db_session: AsyncSession, audience: dict[str, Any],
    caplog: pytest.LogCaptureFixture, rename_file: bool, replace_file: bool,
) -> None:
    from application.notifications.templates import build_email
    from infrastructure.auth import generate_tokens
    from infrastructure.models.notification_delivery import NotificationEventOutbox

    caplog.set_level("DEBUG", logger="carcraft-backend")
    request = audience["request"]
    request.file_url = "https://storage.private/internal-old/key?signature=OLD_SIGNED_SECRET"
    request.file_name = "internal-folder/private/<before>.pdf"
    await db_session.flush()
    body = {"file_url": "https://storage.private/internal-new/key?signature=NEW_SIGNED_SECRET" if replace_file else request.file_url,
        "file_name": r"internal-folder\private\<after>.pdf" if rename_file else request.file_name}
    path = f"/api/v1/exchange/requests/{request.id}"
    dealer_token, _ = generate_tokens(audience["seller"].id, "dealer", audience["dealer"].id)
    denied = await client.patch(path, json=body, headers={"Authorization": f"Bearer {dealer_token}"})
    assert denied.status_code == 403
    assert (await db_session.scalars(select(NotificationEventOutbox))).all() == []
    lc_token, _ = generate_tokens(audience["owner"].id, "leasing_company", audience["lc"].id)
    headers = {"Authorization": f"Bearer {lc_token}"}
    response = await client.patch(path, json=body, headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["request"]["file_url"] == f"{path}/file"
    facts = (await db_session.scalars(select(NotificationEventOutbox))).all()
    assert len(facts) == 1
    fact = facts[0]
    assert fact.event_type == "exchange.request_changed"
    if replace_file:
        assert fact.payload["new_values"]["file_url"] == body["file_url"]
    else:
        assert "file_url" not in fact.payload["new_values"]
    repeated = await client.patch(path, json=body, headers=headers)
    assert repeated.status_code == 200
    assert len((await db_session.scalars(select(NotificationEventOutbox))).all()) == 1
    await process_notification_event(db_session, NotificationEvent.model_validate(fact.payload))
    notices = (await db_session.scalars(select(Notification).where(Notification.event_id == fact.event_id))).all()
    assert {notice.user_id for notice in notices} == {audience[name].id for name in DEALERS | DISTRIBUTORS}
    expected_name = "<after>.pdf" if rename_file else "<before>.pdf"
    for notice in notices:
        assert notice.data is not None
        assert notice.data["attachment_changed"] is True
        assert notice.data["attachment_name"] == expected_name
        assert "Вложение обновлено" in notice.message
        assert notice.data["changed_fields"] == (["file_name"] if rename_file else [])
        if rename_file:
            assert notice.data["previous_values"] == {"file_name": "<before>.pdf"}
            assert notice.data["new_values"] == {"file_name": "<after>.pdf"}
        email = build_email([{"title": notice.title, "message": notice.message,
            "data": notice.data, "action_url": notice.action_url}],
            public_url="https://cabinet.example", timezone="Europe/Moscow")
        assert "Вложение обновлено" in email["body"] and "Вложение обновлено" in email["html"]
        assert expected_name in email["body"]
        assert expected_name not in email["html"]
        assert ("&lt;after&gt;.pdf" if rename_file else "&lt;before&gt;.pdf") in email["html"]
        for secret in ("OLD_SIGNED_SECRET", "NEW_SIGNED_SECRET", "storage.private", "internal-folder", "file_url"):
            assert secret not in str(notice.data) + notice.message + email["body"] + email["html"] + caplog.text
