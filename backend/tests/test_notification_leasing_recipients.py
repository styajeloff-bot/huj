"""The TZ35 leasing matrix against real memberships and object projections."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import pytest
import pytest_asyncio
import sqlalchemy as sa
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from application.notifications.processor import process_notification_event
from application.notifications.recipients import resolve_recipients
from application.queries.leasing_response import (
    GetLcResponseStateQuery,
    handle_get_lc_response_state,
)
from domain.errors import ApplicationNotOwnedError
from domain.events.notifications import NotificationEvent
from infrastructure.auth import generate_tokens
from infrastructure.models.applications import (
    ApplicationVehicle,
    LeasingApplication,
    LeasingCompanyApplication,
)
from infrastructure.models.companies import (
    Company,
    DistributorBrand,
    DistributorDealerLink,
    LeasingCompany,
    LeasingCompanyUser,
)
from infrastructure.models.documents import Document
from infrastructure.models.misc import Notification
from infrastructure.models.notification_delivery import (
    NotificationEmailDelivery,
    NotificationEventOutbox,
)
from infrastructure.models.support import DealerGroup, DealerGroupMember
from infrastructure.models.users import User, UserCompany
from infrastructure.models.vehicles import Warehouse
from infrastructure.repositories import (
    leasing_company_application_repository as lca_repo,
)
from infrastructure.services.object_storage import get_object_storage
from tests.fakes.object_storage import FakeObjectStorage
from tests.legacy_compat import Mark, Vehicle, VehicleWarehouse


@pytest_asyncio.fixture
async def graph(db_session: AsyncSession) -> dict[str, Any]:
    companies = {name: Company(name=name, company_type=kind, is_active=True) for name, kind in [
        ("buyer", "other"), ("dealer", "dealer"), ("other_dealer", "dealer"),
        ("distributor", "distributor"), ("unrelated_distributor", "distributor"),
        ("lc1", "leasing_company"), ("lc2", "leasing_company"), ("unrelated", "other"),
    ]}
    db_session.add_all(companies.values())
    await db_session.flush()
    users: dict[str, User] = {}
    for name, role, company in [
        ("client", "client", "buyer"), ("client_member", "client", "unrelated"),
        ("denied_client", "client", "buyer"), ("inactive_client", "client", "buyer"),
        ("deleted_client", "client", "buyer"), ("outsider", "client", "unrelated"),
        ("dealer", "dealer", "dealer"), ("dealer_colleague", "dealer", "dealer"),
        ("other_dealer", "dealer", "other_dealer"), ("distributor", "distributor", "distributor"),
        ("unrelated_distributor", "distributor", "unrelated_distributor"),
        ("lc1", "leasing_company", "lc1"), ("lc1_explicit", "leasing_company", "unrelated"),
        ("denied_lc", "leasing_company", "lc1"), ("lc2", "leasing_company", "lc2"),
        ("staff", "carcraft_employee", "unrelated"),
    ]:
        users[name] = User(
            name=name, phone=f"+7{uuid4().int % 10**16:016d}",
            email=f"{name}@test.local", role=role, company_id=companies[company].id,
            is_active=name != "inactive_client",
            deleted_at=datetime.now(UTC) if name == "deleted_client" else None,
        )
    db_session.add_all(users.values())
    await db_session.flush()
    for name, company, allowed in [
        ("client_member", "buyer", True), ("denied_client", "buyer", False),
        ("denied_lc", "lc1", False),
    ]:
        db_session.add(UserCompany(
            user_id=users[name].id, company_id=companies[company].id,
            sub_role="administrator", can_view_applications=allowed,
        ))
    lcs = {name: LeasingCompany(company_id=companies[name].id, is_active=True) for name in ("lc1", "lc2")}
    db_session.add_all(lcs.values())
    await db_session.flush()
    db_session.add(LeasingCompanyUser(user_id=users["lc1_explicit"].id, leasing_company_id=lcs["lc1"].id))
    db_session.add(DistributorDealerLink(
        distributor_company_id=companies["distributor"].id,
        dealer_company_id=companies["dealer"].id,
    ))
    brand = Mark(id="notification_faw", name="FAW")
    group = DealerGroup(distributor_company_id=companies["distributor"].id,
        name="Notification dealers", created_by=users["distributor"].id, is_active=True)
    db_session.add_all([brand, group])
    await db_session.flush()
    db_session.add_all([
        DistributorBrand(distributor_company_id=companies["distributor"].id, brand_id=brand.id),
        DealerGroupMember(dealer_group_id=group.id, dealer_company_id=companies["dealer"].id,
                          created_by=users["distributor"].id),
    ])
    app = LeasingApplication(
        company_id=companies["buyer"].id, dealer_company_id=companies["dealer"].id,
        created_by=users["client"].id, status="active", display_number="TZ35-001",
        selected_leasing_companies=[lcs["lc1"].id, lcs["lc2"].id],
    )
    db_session.add(app)
    await db_session.flush()
    db_session.add_all([LeasingCompanyApplication(
        application_id=app.id, leasing_company_id=lc.id, status="under_review",
    ) for lc in lcs.values()])
    lines = {}
    for name in ("dealer", "other_dealer"):
        warehouse = Warehouse(address=name, brand="FAW", company_id=companies[name].id)
        car = Vehicle(base_price=100, is_available=True, mark_id=brand.id)
        db_session.add_all([warehouse, car])
        await db_session.flush()
        db_session.add(VehicleWarehouse(warehouse_id=warehouse.id, vehicle_id=car.id))
        lines[name] = ApplicationVehicle(
            application_id=app.id, vehicle_id=car.id, quantity=1, unit_price=100, total_price=100,
        )
        db_session.add(lines[name])
    await db_session.flush()
    return {"companies": companies, "users": users, "lcs": lcs, "app": app, "lines": lines}


def _event(graph: dict[str, Any], kind: str, *, line: str | None = None) -> NotificationEvent:
    app = graph["app"]
    payload = {"leasing_company_id": str(graph["lcs"]["lc1"].id),
               "selected_leasing_company_id": str(graph["lcs"]["lc1"].id)}
    if line is not None:
        payload["application_vehicle_id"] = str(graph["lines"][line].id)
    return NotificationEvent(
        event_id=uuid4(), event_type=kind, entity_type="leasing_application",
        entity_id=app.id, aggregate_id=app.id, application_id=app.id,
        occurred_at=datetime.now(UTC), request_number=app.display_number,
        actor_user_id=graph["users"]["client"].id, payload=payload,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("kind,names", [
    ("application_created", "dealer dealer_colleague other_dealer staff"),
    ("vehicle_reserved", "client client_member lc1 lc1_explicit lc2 distributor staff"),
    ("vehicle_reservation_expired", "client client_member lc1 lc1_explicit lc2 distributor staff"),
    ("vehicle_cancelled", "client client_member lc1 lc1_explicit lc2 distributor staff"),
    ("additional_price_changed", "client client_member lc1 lc1_explicit"),
    ("company_assigned", "lc1 lc1_explicit"),
    ("application_status_changed", "staff"),
    ("company_selected", "lc1 lc1_explicit staff"),
    ("company_not_selected", "lc2"),
    ("preliminary_offer_accepted", "lc1 lc1_explicit dealer dealer_colleague other_dealer distributor"),
    ("final_offer_accepted", "lc1 lc1_explicit dealer dealer_colleague other_dealer distributor"),
    ("application_cancelled", "client client_member dealer dealer_colleague other_dealer lc1 lc1_explicit lc2 distributor staff"),
    ("company_decision_received", "client client_member dealer dealer_colleague other_dealer distributor staff"),
    ("documents_requested", "client client_member dealer dealer_colleague other_dealer"),
    ("documents_uploaded", "lc1 lc1_explicit"),
    ("application_finalized", "client client_member dealer dealer_colleague other_dealer lc1 lc1_explicit lc2 distributor staff"),
])
async def test_every_leasing_event_has_exact_authorized_recipients(
    db_session: AsyncSession, graph: dict[str, Any], kind: str, names: str,
) -> None:
    event = _event(graph, f"leasing.{kind}", line="dealer" if kind.startswith("vehicle_") else None)
    recipients = await resolve_recipients(db_session, event)
    assert {row["user_id"] for row in recipients} == {graph["users"][name].id for name in names.split()}
    assert len(recipients) == len(names.split())


@pytest.mark.asyncio
async def test_distributor_cannot_receive_a_hidden_child_vehicle_fact(
    db_session: AsyncSession, graph: dict[str, Any],
) -> None:
    recipients = await resolve_recipients(db_session, _event(graph, "leasing.vehicle_reserved", line="other_dealer"))
    assert graph["users"]["distributor"].id not in {row["user_id"] for row in recipients}
    assert graph["users"]["client"].id in {row["user_id"] for row in recipients}


@pytest.mark.asyncio
@pytest.mark.parametrize("suffix", ["response", "financial-bundle", "documents", "accounting-pdf"])
async def test_old_lc_action_link_denies_revoked_permission(
    db_session: AsyncSession, client: AsyncClient, graph: dict[str, Any], suffix: str,
) -> None:
    actor = graph["users"]["lc1"]
    membership = UserCompany(user_id=actor.id, company_id=actor.company_id, can_view_applications=True)
    db_session.add(membership)
    await db_session.flush()
    token, _ = generate_tokens(actor.id, actor.role, actor.company_id)
    event = _event(graph, "leasing.company_assigned")
    assert await resolve_recipients(db_session, event, user_id=actor.id)
    membership.can_view_applications = False
    await db_session.flush()
    assert await resolve_recipients(db_session, event, user_id=actor.id) == []
    response = await client.get(
        f"/api/v1/leasing/applications/{graph['app'].id}/{suffix}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403, response.text


@pytest.mark.asyncio
async def test_user_company_only_lc_member_can_follow_notification_link(
    db_session: AsyncSession, client: AsyncClient, graph: dict[str, Any],
) -> None:
    actor = User(phone=f"+7{uuid4().int % 10**16:016d}", role="leasing_company",
                 company_id=graph["companies"]["unrelated"].id, is_active=True)
    db_session.add(actor)
    await db_session.flush()
    lc_company_id = graph["companies"]["lc1"].id
    db_session.add(UserCompany(user_id=actor.id, company_id=lc_company_id, can_view_applications=True))
    await db_session.flush()
    recipients = await resolve_recipients(db_session, _event(graph, "leasing.company_assigned"), user_id=actor.id)
    assert len(recipients) == 1
    token, _ = generate_tokens(actor.id, actor.role, lc_company_id)
    response = await client.get(
        f"/api/v1/leasing/applications/{graph['app'].id}/response",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["link"]["leasing_company_id"] == str(graph["lcs"]["lc1"].id)
    await db_session.execute(sa.delete(UserCompany).where(UserCompany.user_id == actor.id))
    assert await resolve_recipients(db_session, _event(graph, "leasing.company_assigned"), user_id=actor.id) == []
    response = await client.get(
        f"/api/v1/leasing/applications/{graph['app'].id}/response",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403, response.text


@pytest.mark.asyncio
@pytest.mark.parametrize("revoke", ["user_inactive", "user_deleted", "company_inactive", "lc_inactive", "membership_deleted", "role_changed"])
async def test_lc_action_link_rechecks_current_identity_and_membership(
    db_session: AsyncSession, client: AsyncClient, graph: dict[str, Any], revoke: str,
) -> None:
    actor = graph["users"]["lc1_explicit"]
    company = graph["companies"]["lc1"]
    token, _ = generate_tokens(actor.id, actor.role, company.id)
    if revoke == "user_inactive":
        actor.is_active = False
    elif revoke == "user_deleted":
        actor.deleted_at = datetime.now(UTC)
    elif revoke == "company_inactive":
        company.is_active = False
    elif revoke == "lc_inactive":
        graph["lcs"]["lc1"].is_active = False
    elif revoke == "role_changed":
        actor.role = "client"
    else:
        await db_session.execute(sa.delete(LeasingCompanyUser).where(LeasingCompanyUser.user_id == actor.id))
    await db_session.flush()
    assert await resolve_recipients(db_session, _event(graph, "leasing.company_assigned"), user_id=actor.id) == []
    response = await client.get(
        f"/api/v1/leasing/applications/{graph['app'].id}/response",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403, response.text


@pytest.mark.asyncio
async def test_lc_active_company_context_selects_its_own_response(
    db_session: AsyncSession, client: AsyncClient, graph: dict[str, Any],
) -> None:
    actor = graph["users"]["lc1"]
    lc2 = graph["lcs"]["lc2"]
    db_session.add(UserCompany(user_id=actor.id, company_id=lc2.company_id, can_view_applications=True))
    await db_session.flush()
    token, _ = generate_tokens(actor.id, actor.role, lc2.company_id)
    response = await client.get(
        f"/api/v1/leasing/applications/{graph['app'].id}/response",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["link"]["leasing_company_id"] == str(lc2.id)


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["leasing/applications/{id}/response", "applications/{id}/document-requests", "applications/{id}/documents"])
async def test_explicit_secondary_lc_link_context_is_authorized_per_target(
    db_session: AsyncSession, client: AsyncClient, graph: dict[str, Any], path: str,
) -> None:
    actor = graph["users"]["lc1_explicit"]
    lc = graph["lcs"]["lc1"]
    token, _ = generate_tokens(actor.id, actor.role, actor.company_id)
    url = f"/api/v1/{path.format(id=graph['app'].id)}?leasing_company_id={lc.id}"
    response = await client.get(url, headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200, response.text
    if path.startswith("leasing/"):
        assert response.json()["link"]["leasing_company_id"] == str(lc.id)
    denied_url = f"/api/v1/{path.format(id=graph['app'].id)}?leasing_company_id={graph['lcs']['lc2'].id}"
    response = await client.get(denied_url, headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403, response.text
    db_session.add(UserCompany(user_id=actor.id, company_id=lc.company_id, can_view_applications=False))
    await db_session.flush()
    response = await client.get(url, headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403, response.text


@pytest.mark.asyncio
async def test_lc_document_download_uses_link_context_and_fresh_permission(
    db_session: AsyncSession, client: AsyncClient, graph: dict[str, Any],
) -> None:
    from main import app as http_app

    actor = graph["users"]["lc1_explicit"]
    lc = graph["lcs"]["lc1"]
    doc = Document(company_id=graph["companies"]["buyer"].id, document_type="test",
                   related_application_id=graph["app"].id, file_name="test.pdf", s3_key="test-lc-context")
    db_session.add(doc)
    await db_session.flush()
    storage = FakeObjectStorage()
    await storage.put("test-lc-context", b"private LC document", "application/pdf")
    http_app.dependency_overrides[get_object_storage] = lambda: storage
    token, _ = generate_tokens(actor.id, actor.role, actor.company_id)
    url = f"/api/v1/documents/{doc.id}/content?leasing_company_id={lc.id}"
    response = await client.get(url, headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200, response.text
    assert response.content == b"private LC document"
    db_session.add(UserCompany(user_id=actor.id, company_id=lc.company_id, can_view_applications=False))
    await db_session.flush()
    response = await client.get(url, headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403, response.text


@pytest.mark.asyncio
async def test_alternate_lca_reads_do_not_bypass_lc_access(
    db_session: AsyncSession, client: AsyncClient, graph: dict[str, Any],
) -> None:
    actor = graph["users"]["lc1"]
    token, _ = generate_tokens(actor.id, actor.role, actor.company_id)
    other_link = await db_session.scalar(sa.select(LeasingCompanyApplication.id).where(
        LeasingCompanyApplication.application_id == graph["app"].id,
        LeasingCompanyApplication.leasing_company_id == graph["lcs"]["lc2"].id,
    ))
    response = await client.get(f"/api/v1/leasing-company-applications/{other_link}", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403, response.text
    db_session.add(UserCompany(user_id=actor.id, company_id=actor.company_id, can_view_applications=False))
    await db_session.flush()
    response = await client.get("/api/v1/leasing-company-applications/", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403, response.text


@pytest.mark.asyncio
async def test_lc_query_itself_enforces_fresh_permission(
    db_session: AsyncSession, graph: dict[str, Any],
) -> None:
    actor = graph["users"]["denied_lc"]
    with pytest.raises(ApplicationNotOwnedError):
        await handle_get_lc_response_state(
            GetLcResponseStateQuery(
                application_id=graph["app"].id,
                actor_user_id=actor.id, actor_company_id=actor.company_id,
                actor_leasing_company_id=graph["lcs"]["lc1"].id,
            ), db_session,
        )


@pytest.mark.asyncio
async def test_legacy_lc_resolution_does_not_replace_exact_http_policy(
    db_session: AsyncSession, client: AsyncClient, graph: dict[str, Any],
) -> None:
    actor = graph["users"]["lc1"]
    lc2 = graph["lcs"]["lc2"]
    assert await lca_repo.resolve_lc_id_for_user(db_session, actor.id) == graph["lcs"]["lc1"].id
    db_session.add(LeasingCompanyUser(user_id=actor.id, leasing_company_id=lc2.id))
    db_session.add(UserCompany(user_id=actor.id, company_id=lc2.company_id, can_view_applications=False))
    await db_session.flush()
    # Unrelated legacy workflows retain explicit-binding precedence; this
    # mapping helper is not the authorization seam for notification links.
    assert await lca_repo.resolve_lc_id_for_user(db_session, actor.id) == lc2.id
    token, _ = generate_tokens(actor.id, actor.role, actor.company_id)
    response = await client.get(
        f"/api/v1/leasing/applications/{graph['app'].id}/response?leasing_company_id={lc2.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403, response.text


@pytest.mark.asyncio
async def test_explicit_lc_context_writes_only_authorized_branch(
    db_session: AsyncSession, client: AsyncClient, graph: dict[str, Any],
) -> None:
    actor = graph["users"]["lc1_explicit"]
    token, _ = generate_tokens(actor.id, actor.role, actor.company_id)
    links = (await db_session.scalars(sa.select(LeasingCompanyApplication).where(
        LeasingCompanyApplication.application_id == graph["app"].id,
    ))).all()
    by_lc = {row.leasing_company_id: row for row in links}
    for link in links:
        link.status = "submitted"
    await db_session.flush()
    lc1 = graph["lcs"]["lc1"]
    lc2 = graph["lcs"]["lc2"]
    base_url = f"/api/v1/leasing/applications/{graph['app'].id}/take-in-work"
    response = await client.post(f"{base_url}?leasing_company_id={lc2.id}", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403, response.text
    await db_session.refresh(by_lc[lc2.id])
    assert by_lc[lc2.id].status == "submitted"
    response = await client.post(f"{base_url}?leasing_company_id={lc1.id}", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200, response.text
    assert response.json()["lca_id"] == str(by_lc[lc1.id].id)
    await db_session.refresh(by_lc[lc1.id])
    assert by_lc[lc1.id].status == "under_review"
    db_session.add(UserCompany(user_id=actor.id, company_id=lc1.company_id, can_view_applications=False))
    await db_session.flush()
    response = await client.post(f"{base_url}?leasing_company_id={lc1.id}", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403, response.text


async def _secondary_company_actor(
    session: AsyncSession, graph: dict[str, Any], role: str,
) -> tuple[User, UserCompany]:
    actor = User(phone=f"+7{uuid4().int % 10**16:016d}", role=role,
                 company_id=graph["companies"]["unrelated"].id, is_active=True)
    session.add(actor)
    await session.flush()
    target = graph["companies"]["buyer" if role == "client" else role]
    membership = UserCompany(user_id=actor.id, company_id=target.id,
                             can_view_applications=True, can_create_applications=True)
    session.add(membership)
    await session.flush()
    return actor, membership


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["client", "dealer", "distributor"])
async def test_secondary_company_inbox_action_opens_exact_authorized_application(
    db_session: AsyncSession, client: AsyncClient, graph: dict[str, Any], role: str,
) -> None:
    actor, membership = await _secondary_company_actor(db_session, graph, role)
    event = _event(graph, "leasing.application_finalized")
    await process_notification_event(db_session, event)
    token, _ = generate_tokens(actor.id, actor.role, actor.company_id)
    headers = {"Authorization": f"Bearer {token}"}
    legacy_response = await client.get(f"/api/v1/applications/{event.aggregate_id}", headers=headers)
    assert legacy_response.status_code in {403, 404}, legacy_response.text
    inbox = await client.get("/api/v1/notifications", headers=headers)
    assert inbox.status_code == 200, inbox.text
    notification = next(row for row in inbox.json()["notifications"] if row["event_id"] == str(event.event_id))
    action_query = urlsplit(notification["action_url"]).query
    assert parse_qs(action_query)["notification_company_id"] == [str(membership.company_id)]
    # The UI action opens this application's detail and forwards its verified
    # context query, without rewriting the user's globally selected company.
    url = f"/api/v1/applications/{event.aggregate_id}?{action_query}"
    response = await client.get(url, headers=headers)
    assert response.status_code == 200, response.text
    visible_ids = {row["id"] for row in response.json()["vehicles"]}
    expected_lines = ("dealer", "other_dealer") if role == "client" else ("dealer",)
    assert visible_ids == {str(graph["lines"][name].id) for name in expected_lines}
    doc = Document(company_id=membership.company_id, document_type="notification-context",
                   related_application_id=graph["app"].id, file_name="context.pdf")
    db_session.add(doc)
    await db_session.flush()
    document_url = f"/api/v1/documents/{doc.id}?{action_query}"
    document_response = await client.get(document_url, headers=headers)
    # Context selection does not grant the DOCUMENTS_READ scope to distributors.
    assert document_response.status_code == (403 if role == "distributor" else 200), document_response.text
    if role != "distributor":
        assert document_response.json()["id"] == str(doc.id)
    await db_session.refresh(actor)
    assert actor.company_id == graph["companies"]["unrelated"].id
    unrelated = await client.get(f"/api/v1/applications/{event.aggregate_id}?notification_company_id={uuid4()}", headers=headers)
    assert unrelated.status_code == 403, unrelated.text
    membership.can_view_applications = False
    await db_session.flush()
    assert await resolve_recipients(db_session, event, user_id=actor.id) == []
    revoked = await client.get(url, headers=headers)
    assert revoked.status_code == 403, revoked.text
    revoked_document = await client.get(document_url, headers=headers)
    assert revoked_document.status_code == 403, revoked_document.text


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["dealer", "distributor"])
async def test_secondary_company_vehicle_actions_preserve_hidden_child_boundary(
    db_session: AsyncSession, client: AsyncClient, graph: dict[str, Any], role: str,
) -> None:
    actor, membership = await _secondary_company_actor(db_session, graph, role)
    token, _ = generate_tokens(actor.id, actor.role, actor.company_id)
    headers = {"Authorization": f"Bearer {token}"}
    query = f"notification_company_id={membership.company_id}"
    hidden = graph["lines"]["other_dealer"]
    visible = graph["lines"]["dealer"]
    before_events = await db_session.scalar(sa.select(sa.func.count()).select_from(NotificationEventOutbox))
    response = await client.post(f"/api/v1/application-vehicles/{hidden.id}/dealer-action?{query}", headers=headers, json={"action": "reserve"})
    assert response.status_code == 403, response.text
    await db_session.refresh(hidden)
    assert hidden.car_status == "active"
    assert await db_session.scalar(sa.select(sa.func.count()).select_from(NotificationEventOutbox)) == before_events
    response = await client.get(f"/api/v1/application-vehicles/{hidden.id}/available-vins?{query}", headers=headers)
    assert response.status_code in {403, 404}, response.text
    response = await client.get(f"/api/v1/application-vehicles/{visible.id}/available-vins?{query}", headers=headers)
    assert response.status_code == 200, response.text
    response = await client.post(f"/api/v1/application-vehicles/{visible.id}/dealer-action?{query}", headers=headers, json={"action": "reserve"})
    assert response.status_code == 409, response.text
    membership.can_view_applications = False
    await db_session.flush()
    response = await client.post(f"/api/v1/application-vehicles/{visible.id}/dealer-action?{query}", headers=headers, json={"action": "reject"})
    assert response.status_code == 403, response.text
    await db_session.refresh(visible)
    assert visible.car_status == "active"


@pytest.mark.asyncio
async def test_company_and_lc_selectors_must_describe_the_same_context(
    db_session: AsyncSession, client: AsyncClient, graph: dict[str, Any],
) -> None:
    actor = graph["users"]["lc1_explicit"]
    lc1 = graph["lcs"]["lc1"]
    lc2 = graph["lcs"]["lc2"]
    db_session.add(UserCompany(user_id=actor.id, company_id=lc2.company_id, can_view_applications=True))
    await db_session.flush()
    token, _ = generate_tokens(actor.id, actor.role, actor.company_id)
    base_url = f"/api/v1/leasing/applications/{graph['app'].id}/response"
    matched = await client.get(f"{base_url}?leasing_company_id={lc1.id}&notification_company_id={lc1.company_id}", headers={"Authorization": f"Bearer {token}"})
    assert matched.status_code == 200, matched.text
    assert matched.json()["link"]["leasing_company_id"] == str(lc1.id)
    conflicting = await client.get(f"{base_url}?leasing_company_id={lc1.id}&notification_company_id={lc2.company_id}", headers={"Authorization": f"Bearer {token}"})
    assert conflicting.status_code == 403, conflicting.text


@pytest.mark.asyncio
@pytest.mark.parametrize("revoke", ["inactive", "deleted", "role_changed"])
async def test_no_selector_preserves_staff_access_but_rechecks_current_identity(
    db_session: AsyncSession, client: AsyncClient, graph: dict[str, Any], revoke: str,
) -> None:
    actor = graph["users"]["staff"]
    token, _ = generate_tokens(actor.id, actor.role, actor.company_id)
    url = f"/api/v1/applications/{graph['app'].id}"
    headers = {"Authorization": f"Bearer {token}"}
    response = await client.get(url, headers=headers)
    assert response.status_code == 200, response.text
    assert len(response.json()["vehicles"]) == 2
    if revoke == "inactive":
        actor.is_active = False
    elif revoke == "deleted":
        actor.deleted_at = datetime.now(UTC)
    else:
        actor.role = "client"
    await db_session.flush()
    response = await client.get(url, headers=headers)
    assert response.status_code == 403, response.text


@pytest.mark.asyncio
@pytest.mark.parametrize("target", [
    "applications/{id}", "applications", "leasing-company-applications/",
    "application-vehicles/{vehicle}/available-vins",
    "applications/{id}/leasing-responses", "applications/{id}/sopd-signer-candidates",
    "applications/{id}/export.pdf", "applications/{id}/documents",
])
async def test_distributor_read_revoke_cannot_be_bypassed_by_removing_company_selector(
    db_session: AsyncSession, client: AsyncClient, graph: dict[str, Any], target: str,
) -> None:
    actor = graph["users"]["distributor"]
    membership = UserCompany(user_id=actor.id, company_id=actor.company_id,
                             can_view_applications=True, can_create_applications=True)
    db_session.add(membership)
    await db_session.flush()
    token, _ = generate_tokens(actor.id, actor.role, actor.company_id)
    headers = {"Authorization": f"Bearer {token}"}
    detail = f"/api/v1/applications/{graph['app'].id}"
    allowed = await client.get(detail, headers=headers)
    assert allowed.status_code == 200, allowed.text
    assert {row["id"] for row in allowed.json()["vehicles"]} == {str(graph["lines"]["dealer"].id)}
    event = _event(graph, "leasing.vehicle_reserved", line="dealer")
    assert await resolve_recipients(db_session, event, user_id=actor.id)
    membership.can_view_applications = False
    await db_session.flush()
    assert await resolve_recipients(db_session, event, user_id=actor.id) == []
    url = f"/api/v1/{target.format(id=graph['app'].id, vehicle=graph['lines']['dealer'].id)}"
    for suffix in (f"?notification_company_id={actor.company_id}", ""):
        response = await client.get(url + suffix, headers=headers)
        assert response.status_code == 403, (response.status_code, target, suffix)


@pytest.mark.asyncio
async def test_consumer_fanout_replay_and_role_routes(
    db_session: AsyncSession, graph: dict[str, Any],
) -> None:
    event = _event(graph, "leasing.application_finalized")
    first = await process_notification_event(db_session, event)
    assert len(first) == 10
    assert await process_notification_event(db_session, event) == []
    rows = (await db_session.scalars(sa.select(Notification).where(Notification.event_id == event.event_id))).all()
    deliveries = (await db_session.scalars(sa.select(NotificationEmailDelivery).where(
        NotificationEmailDelivery.event_id == event.event_id,
    ))).all()
    assert len(rows) == len(deliveries) == 10
    by_user = {row.user_id: row for row in rows}
    assert all(row.is_read is False and row.read_at is None for row in rows)
    assert by_user[graph["users"]["lc1_explicit"].id].action_url == (
        f"/workspace/leasing-applications/{event.aggregate_id}?leasing_company_id={graph['lcs']['lc1'].id}"
    )
    assert by_user[graph["users"]["dealer"].id].action_url == (
        f"/workspace/applications?application={event.aggregate_id}&notification_company_id={graph['companies']['dealer'].id}"
    )
    client_route = by_user[graph["users"]["client"].id].action_url
    assert client_route is not None and urlsplit(client_route).path.endswith(f"/application/{event.aggregate_id}")
    assert parse_qs(urlsplit(client_route).query)["notification_company_id"] == [str(graph["companies"]["buyer"].id)]
