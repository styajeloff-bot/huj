"""Integration tests for the G4 dealer cabinet additions (profile / clients / inventory / reports)."""
from __future__ import annotations

from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.auth import generate_tokens
from infrastructure.models.applications import LeasingApplication
from infrastructure.models.companies import Company
from infrastructure.models.users import User
from tests.legacy_compat import CarModel, Mark, Vehicle

pytestmark = pytest.mark.asyncio


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def dealer_with_company(
    db_session: AsyncSession,
) -> tuple[User, Company, str]:
    c = Company(name="Дилер Ко", inn="7710999001", company_type="dealer")
    db_session.add(c)
    await db_session.flush()

    u = User(
        phone="+76660007701",
        email="dealer-g4@test.local",
        name="Router Dealer",
        role="dealer",
        company_id=c.id,
        is_active=True,
    )
    db_session.add(u)
    await db_session.flush()
    await db_session.refresh(u)
    token, _ = generate_tokens(u.id, "dealer", c.id)
    return u, c, token


# NOTE: /dealer/profile endpoints were consolidated into /users/me in
# Phase 13 R13a. Tests for the unified surface live in
# tests/integration/test_users_me_router.py.


async def test_get_clients_filters_by_dealer(
    client: AsyncClient,
    db_session: AsyncSession,
    dealer_with_company: tuple[User, Company, str],
) -> None:
    _user, company, token = dealer_with_company

    # Seed two clients via email matching
    c1 = User(phone="+79000000110", email="clA@x.y", role="client", is_active=True)
    c2 = User(phone="+79000000111", email="clB@x.y", role="client", is_active=True)
    db_session.add_all([c1, c2])
    await db_session.flush()

    db_session.add_all(
        [
            LeasingApplication(
                company_id=company.id,
                email=c1.email,
                total_amount=Decimal("10"),
                status="active",
            ),
            LeasingApplication(
                company_id=company.id,
                email=c2.email,
                total_amount=Decimal("20"),
                status="active",
            ),
        ]
    )
    await db_session.flush()

    response = await client.get(
        "/api/v1/dealer/clients", headers=_auth(token)
    )
    assert response.status_code == 200
    body = response.json()
    emails = [x["email"] for x in body["clients"]]
    assert set(emails) == {c1.email, c2.email}


async def test_inventory_alias_list_delegates(
    client: AsyncClient,
    db_session: AsyncSession,
    dealer_with_company: tuple[User, Company, str],
    default_vehicle_category_id: str,
) -> None:
    _user, company, token = dealer_with_company
    mark = Mark(id="mark_inv", name="Mark Inv")
    db_session.add(mark)
    await db_session.flush()
    model = CarModel(
        id="model_inv",
        name="Model Inv",
        mark_id=mark.id,
        category=default_vehicle_category_id,
    )
    db_session.add(model)
    await db_session.flush()

    v = Vehicle(
        dealer_id=company.id,
        status="available",
        is_available=True,
        mark_id=mark.id,
        model_id=model.id,
        base_price=Decimal("100"),
    )
    db_session.add(v)
    await db_session.flush()

    response = await client.get(
        "/api/v1/dealer/inventory", headers=_auth(token)
    )
    assert response.status_code == 200
    ids = [item["id"] for item in response.json()["vehicles"]]
    assert str(v.id) in ids


async def test_inventory_post_and_delete_flow(
    client: AsyncClient,
    db_session: AsyncSession,
    dealer_with_company: tuple[User, Company, str],
    default_vehicle_category_id: str,
) -> None:
    _user, _, token = dealer_with_company
    del _user
    mark = Mark(id="mark_post", name="Mark P")
    db_session.add(mark)
    await db_session.flush()
    model = CarModel(
        id="model_post",
        name="Model P",
        mark_id=mark.id,
        category=default_vehicle_category_id,
    )
    db_session.add(model)
    await db_session.flush()

    created = await client.post(
        "/api/v1/dealer/inventory",
        headers=_auth(token),
        json={
            "mark_id": mark.id,
            "model_id": model.id,
            "year": 2024,
            "base_price": "100000.00",
        },
    )
    assert created.status_code == 201, created.text
    vehicle_id = created.json()["vehicle"]["id"]

    deleted = await client.delete(
        f"/api/v1/dealer/inventory/{vehicle_id}",
        headers=_auth(token),
    )
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["id"] == vehicle_id


async def test_reports_shim_returns_payload(
    client: AsyncClient,
    db_session: AsyncSession,
    dealer_with_company: tuple[User, Company, str],
) -> None:
    _, _, token = dealer_with_company
    response = await client.get(
        "/api/v1/dealer/reports", headers=_auth(token)
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert "reports" in body


async def test_reports_xlsx_format_returns_streaming_file(
    client: AsyncClient,
    dealer_with_company: tuple[User, Company, str],
) -> None:
    _, _, token = dealer_with_company
    response = await client.get(
        "/api/v1/dealer/reports?format=xlsx", headers=_auth(token)
    )
    assert response.status_code == 200, response.text
    assert (
        "spreadsheetml.sheet" in response.headers["content-type"]
    )
    assert "attachment" in response.headers["content-disposition"]
    assert len(response.content) > 0


async def test_reports_csv_format_returns_streaming_file(
    client: AsyncClient,
    dealer_with_company: tuple[User, Company, str],
) -> None:
    _, _, token = dealer_with_company
    response = await client.get(
        "/api/v1/dealer/reports?format=csv", headers=_auth(token)
    )
    assert response.status_code == 200, response.text
    assert "text/csv" in response.headers["content-type"]
    assert "attachment" in response.headers["content-disposition"]
