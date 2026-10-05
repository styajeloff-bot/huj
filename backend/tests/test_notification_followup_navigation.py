"""TZ35 notification navigation and real HTTP filter regressions."""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from domain.events.notifications import EventType, NotificationEvent
from domain.notification_policy import action_route, normalize_inbox_action_url
from infrastructure.models.applications import LeasingApplication
from infrastructure.models.companies import Company
from infrastructure.models.misc import Notification
from infrastructure.models.storefronts import Storefront
from infrastructure.models.users import User
from infrastructure.repositories.notification_recipients_repository import (
    leasing_context,
)


async def test_recipient_context_loads_the_applications_actual_storefront(db_session: AsyncSession) -> None:
    company = Company(name="Storefront notification owner", company_type="other")
    storefront = Storefront(slug="tz35-target", is_default=False, is_active=True, version=1)
    other_storefront = Storefront(slug="tz35-other", is_default=False, is_active=True, version=1)
    db_session.add_all([company, storefront, other_storefront])
    await db_session.flush()
    app = LeasingApplication(company_id=company.id, storefront_id=storefront.id, status="active")
    db_session.add(app)
    await db_session.flush()
    context = await leasing_context(db_session, app.id)
    assert context is not None
    assert context["application"]["id"] == app.id
    assert context["storefront_slug"] == "tz35-target"


@pytest.mark.parametrize("kind", [
    "exchange_new_request", "exchange_new_bid", "exchange_bid_updated",
    "exchange_bid_accepted", "exchange_request_changed", "exchange_bid_withdrawn",
    "exchange_deadline", "exchange_request_finalized", "exchange_bid_not_selected",
])
async def test_exchange_http_filter_returns_matching_owned_notifications(
    client: AsyncClient, client_token: str, client_user: User, other_user: User,
    db_session: AsyncSession, kind: str,
) -> None:
    own_id = uuid4()
    db_session.add_all([
        Notification(id=own_id, user_id=client_user.id, type=kind, title="Own", message="Own"),
        Notification(user_id=other_user.id, type=kind, title="Other", message="Other"),
        Notification(user_id=client_user.id, type="system", title="System", message="System"),
    ])
    await db_session.flush()
    headers = {"Authorization": f"Bearer {client_token}"}
    unfiltered = await client.get("/api/v1/notifications", headers=headers)
    assert unfiltered.status_code == 200
    assert str(own_id) in {item["id"] for item in unfiltered.json()["notifications"]}
    filtered = await client.get(
        "/api/v1/notifications", headers=headers, params={"notification_type": kind},
    )
    assert filtered.status_code == 200
    assert [item["id"] for item in filtered.json()["notifications"]] == [str(own_id)]
    assert filtered.json()["pagination"]["total"] == 1


@pytest.mark.parametrize("event_type,status,section", [
    ("leasing.company_decision_received", "approved_scoring", "preliminary"),
    ("leasing.company_decision_received", "approved_scoring_another_cond", "preliminary"),
    ("leasing.company_decision_received", "approved_final", "final"),
    ("leasing.company_decision_received", "approved_final_another_cond", "final"),
    ("leasing.company_decision_received", "rejected_prescoring", None),
    ("leasing.company_decision_received", "rejected_approved", None),
    ("leasing.documents_requested", "documents_required", "documents"),
])
def test_client_notification_route_opens_semantic_section(
    event_type: EventType, status: str, section: str | None,
) -> None:
    application_id = UUID("d1b18503-3775-4330-b2ab-81c563c14351")
    company_id = UUID("462b738a-e78c-4f93-bbdc-6522a00cefaf")
    event = NotificationEvent(
        event_id=uuid4(), event_type=event_type, entity_type="leasing_application",
        entity_id=application_id, aggregate_id=application_id, application_id=application_id,
        request_number="TZ35-FOLLOWUP", occurred_at=datetime.now(UTC),
        changed_fields=["lca_status"], new_values={"lca_status": status},
        payload={"leasing_company_id": str(uuid4())},
    )
    expected_query = f"notification_company_id={company_id}"
    if section is not None:
        expected_query += f"&section={section}"
    assert action_route(event, "client", "faw", company_id=company_id) == (
        f"/faw/application/{application_id}?{expected_query}"
    )
    assert action_route(event, "dealer", company_id=company_id) == (
        f"/workspace/applications?application={application_id}&notification_company_id={company_id}"
    )


@pytest.mark.parametrize("event_type,status,section", [
    ("leasing.company_decision_received", "approved_scoring", "preliminary"),
    ("leasing.company_decision_received", "approved_final", "final"),
    ("leasing.documents_requested", "documents_required", "documents"),
])
async def test_historical_inbox_route_is_projected_without_rewriting_read_record(
    client: AsyncClient, client_token: str, client_user: User, db_session: AsyncSession,
    event_type: str, status: str, section: str,
) -> None:
    company = Company(name="Notification owner", company_type="other")
    db_session.add(company)
    await db_session.flush()
    app = LeasingApplication(company_id=company.id, status="active")
    db_session.add(app)
    await db_session.flush()
    old_url = (
        f"/faw/application/{app.id}?notification_company_id={company.id}&filter=one&filter=two"
        "&comment=%D0%BF%D1%80%D0%BE%D0%B2%D0%B5%D1%80%D0%BA%D0%B0&step=4#details"
    )
    read_at = datetime.now(UTC)
    row = Notification(
        user_id=client_user.id, type="leasing_approval", title="Historical", message="Historical",
        application_id=app.id, action_url=old_url, is_read=True, read_at=read_at,
        data={"event_type": event_type, "entity_type": "leasing_application",
              "entity_id": str(app.id), "new_values": {"lca_status": status}},
    )
    db_session.add(row)
    await db_session.flush()
    response = await client.get("/api/v1/notifications", headers={"Authorization": f"Bearer {client_token}"})
    assert response.status_code == 200
    [item] = response.json()["notifications"]
    assert item["action_url"] == old_url.replace("step=4", f"section={section}")
    assert item["is_read"] is True
    assert datetime.fromisoformat(item["read_at"]) == read_at
    await db_session.refresh(row)
    assert row.action_url == old_url
    assert row.read_at == read_at


@pytest.mark.parametrize("url", [
    "https://outside.example/application/d1b18503-3775-4330-b2ab-81c563c14351",
    "https://[invalid", "//outside.example/path", "/\\outside.example/path",
    "/faw/../application/d1b18503-3775-4330-b2ab-81c563c14351",
    "/application/462b738a-e78c-4f93-bbdc-6522a00cefaf",
    "/application/d1b18503-3775-4330-b2ab-81c563c14351?notification_company_id=462b738a-e78c-4f93-bbdc-6522a00cefaf",
    "/application/d1b18503-3775-4330-b2ab-81c563c14351?step=5%09",
    "/application/d1b18503-3775-4330-b2ab-81c563c14351?step=5%7F",
    "/workspace/applications?application=d1b18503-3775-4330-b2ab-81c563c14351",
])
def test_historical_projection_does_not_rewrite_manual_external_or_other_targets(url: str) -> None:
    application_id = UUID("d1b18503-3775-4330-b2ab-81c563c14351")
    data = {"event_type": "leasing.company_decision_received", "entity_type": "leasing_application",
            "entity_id": str(application_id), "new_values": {"lca_status": "approved_final"}}
    assert normalize_inbox_action_url(url, application_id, data) == url


async def test_http_filters_compose_and_keep_global_counts(
    client: AsyncClient, client_token: str, client_user: User, other_user: User, db_session: AsyncSession,
) -> None:
    now = datetime.now(UTC)
    older_id = uuid4()
    common = {"user_id": client_user.id, "type": "exchange_new_bid", "title": "Notice", "message": "Notice"}
    db_session.add_all([
        Notification(**common, created_at=now),
        Notification(**common, id=older_id, created_at=now - timedelta(minutes=10)),
        Notification(**common, is_read=True, created_at=now),
        Notification(**common, deleted_at=now, created_at=now),
        Notification(**common, created_at=now - timedelta(days=40)),
        Notification(**(common | {"user_id": other_user.id}), created_at=now),
        Notification(**(common | {"type": "system"}), created_at=now),
    ])
    await db_session.flush()
    headers = {"Authorization": f"Bearer {client_token}"}
    filtered = await client.get("/api/v1/notifications", headers=headers, params={
        "notification_type": "exchange_new_bid", "is_read": "false", "period": "week", "page": 2, "limit": 1,
    })
    assert filtered.status_code == 200
    assert [item["id"] for item in filtered.json()["notifications"]] == [str(older_id)]
    assert filtered.json()["pagination"] == {"page": 2, "limit": 1, "total": 2, "pages": 2}
    counts = await client.get("/api/v1/notifications?fields=count", headers=headers)
    assert counts.json() == {"total_count": 5, "unread_count": 4}
    invalid = await client.get("/api/v1/notifications?notification_type=unknown", headers=headers)
    assert invalid.status_code == 422
    empty = await client.get("/api/v1/notifications?notification_type=exchange_bid_withdrawn", headers=headers)
    assert empty.status_code == 200
    assert empty.json()["notifications"] == []
