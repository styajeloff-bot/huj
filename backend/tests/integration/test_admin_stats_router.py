"""Integration tests for /api/v1/admin/stats + /leasing-companies + /dealers (F2)."""
from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.models.companies import Company, LeasingCompany
from infrastructure.models.users import User

pytestmark = pytest.mark.asyncio


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def sample_leasing_company(
    db_session: AsyncSession,
) -> LeasingCompany:
    company = Company(
        name="Stats LC",
        inn="7799003001",
        company_type="leasing_company",
        is_active=True,
    )
    db_session.add(company)
    await db_session.flush()
    lc = LeasingCompany(company_id=company.id, is_active=True)
    db_session.add(lc)
    await db_session.flush()
    return lc


@pytest_asyncio.fixture
async def sample_dealer(db_session: AsyncSession) -> User:
    user = User(
        phone="+76660003001",
        email="stats-dealer@test.local",
        name="Stats Dealer",
        role="dealer",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    return user


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


async def test_get_stats_happy(
    client: AsyncClient, employee_token: str
) -> None:
    response = await client.get(
        "/api/v1/admin/stats", headers=_auth(employee_token)
    )
    assert response.status_code == 200
    body = response.json()
    assert "users_by_role" in body
    assert "companies_by_type" in body
    assert "applications_by_status" in body
    assert "total_vehicles" in body


async def test_get_stats_anon_unauthorised(client: AsyncClient) -> None:
    response = await client.get("/api/v1/admin/stats")
    assert response.status_code == 401


async def test_get_stats_client_forbidden(
    client: AsyncClient, client_token: str
) -> None:
    response = await client.get(
        "/api/v1/admin/stats", headers=_auth(client_token)
    )
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# Leasing companies directory
# ---------------------------------------------------------------------------


async def test_list_leasing_companies_happy(
    client: AsyncClient,
    employee_token: str,
    sample_leasing_company: LeasingCompany,
) -> None:
    response = await client.get(
        "/api/v1/admin/leasing-companies",
        headers=_auth(employee_token),
    )
    assert response.status_code == 200
    body = response.json()
    assert "companies" in body
    assert any(
        str(c["id"]) == str(sample_leasing_company.id) for c in body["companies"]
    )


async def test_list_leasing_companies_anon_unauthorised(
    client: AsyncClient,
) -> None:
    response = await client.get("/api/v1/admin/leasing-companies")
    assert response.status_code == 401


async def test_list_leasing_companies_client_forbidden(
    client: AsyncClient, client_token: str
) -> None:
    response = await client.get(
        "/api/v1/admin/leasing-companies",
        headers=_auth(client_token),
    )
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# Dealers directory
# ---------------------------------------------------------------------------


async def test_list_dealers_happy(
    client: AsyncClient,
    employee_token: str,
    sample_dealer: User,
) -> None:
    response = await client.get(
        "/api/v1/admin/dealers", headers=_auth(employee_token)
    )
    assert response.status_code == 200
    body = response.json()
    assert "dealers" in body
    assert any(d["id"] == str(sample_dealer.id) for d in body["dealers"])


async def test_list_dealers_anon_unauthorised(client: AsyncClient) -> None:
    response = await client.get("/api/v1/admin/dealers")
    assert response.status_code == 401


async def test_list_dealers_client_forbidden(
    client: AsyncClient, client_token: str
) -> None:
    response = await client.get(
        "/api/v1/admin/dealers", headers=_auth(client_token)
    )
    assert response.status_code == 403
