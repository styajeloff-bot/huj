"""Integration tests for /api/v1/companies/* (read-only profile endpoints)."""
from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.models.companies import Company, Distributor, LeasingCompany
from infrastructure.models.users import User, UserCompany

pytestmark = pytest.mark.asyncio


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _make_company(
    db: AsyncSession,
    *,
    name: str = "Тест Ко",
    inn: str = "7710000001",
    company_type: str = "dealer",
) -> Company:
    company = Company(
        name=name,
        inn=inn,
        company_type=company_type,
        is_active=True,
    )
    db.add(company)
    await db.flush()
    await db.refresh(company)
    return company


# ---------------------------------------------------------------------------
# GET /api/v1/companies/profile  (current user's company)
# ---------------------------------------------------------------------------


async def test_my_profile_unauthenticated_is_401(client: AsyncClient) -> None:
    response = await client.get("/api/v1/companies/profile")
    assert response.status_code == 401


async def test_my_profile_404_when_no_link(
    client: AsyncClient, client_token: str
) -> None:
    response = await client.get(
        "/api/v1/companies/profile", headers=_auth(client_token)
    )
    assert response.status_code == 404


async def test_my_profile_returns_linked_company(
    client: AsyncClient,
    client_token: str,
    client_user: User,
    db_session: AsyncSession,
) -> None:
    company = await _make_company(db_session, inn="7710000002")
    client_user.company_id = company.id
    await db_session.flush()

    response = await client.get(
        "/api/v1/companies/profile", headers=_auth(client_token)
    )
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(company.id)
    assert body["inn"] == "7710000002"
    assert body["company_type"] == "dealer"


async def test_my_profile_includes_leasing_extension(
    client: AsyncClient,
    client_token: str,
    client_user: User,
    db_session: AsyncSession,
) -> None:
    company = await _make_company(
        db_session, inn="7710000003", company_type="leasing_company"
    )
    db_session.add(
        LeasingCompany(
            company_id=company.id, min_down_payment_percent=15
        )
    )
    client_user.company_id = company.id
    await db_session.flush()

    response = await client.get(
        "/api/v1/companies/profile", headers=_auth(client_token)
    )
    assert response.status_code == 200
    body = response.json()
    assert body["leasing_company"]["min_down_payment_percent"] == 15


# ---------------------------------------------------------------------------
# GET /api/v1/companies/{id}/profile
# ---------------------------------------------------------------------------


async def test_profile_by_id_unauthenticated_is_401(
    client: AsyncClient,
) -> None:
    response = await client.get("/api/v1/companies/1/profile")
    assert response.status_code == 401


async def test_profile_by_id_employee_can_read_any(
    client: AsyncClient,
    employee_token: str,
    db_session: AsyncSession,
) -> None:
    company = await _make_company(db_session, inn="7710000004")
    response = await client.get(
        f"/api/v1/companies/{company.id}/profile",
        headers=_auth(employee_token),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(company.id)
    assert body["inn"] == "7710000004"


async def test_profile_by_id_owner_via_users_company_id(
    client: AsyncClient,
    client_token: str,
    client_user: User,
    db_session: AsyncSession,
) -> None:
    company = await _make_company(db_session, inn="7710000005")
    client_user.company_id = company.id
    await db_session.flush()

    response = await client.get(
        f"/api/v1/companies/{company.id}/profile",
        headers=_auth(client_token),
    )
    assert response.status_code == 200
    assert response.json()["id"] == str(company.id)


async def test_profile_by_id_owner_via_user_companies_join(
    client: AsyncClient,
    client_token: str,
    client_user: User,
    db_session: AsyncSession,
) -> None:
    company = await _make_company(db_session, inn="7710000006")
    db_session.add(
        UserCompany(user_id=client_user.id, company_id=company.id)
    )
    await db_session.flush()

    response = await client.get(
        f"/api/v1/companies/{company.id}/profile",
        headers=_auth(client_token),
    )
    assert response.status_code == 200
    assert response.json()["id"] == str(company.id)


async def test_profile_by_id_stranger_is_403(
    client: AsyncClient,
    other_token: str,
    db_session: AsyncSession,
) -> None:
    company = await _make_company(db_session, inn="7710000007")
    response = await client.get(
        f"/api/v1/companies/{company.id}/profile",
        headers=_auth(other_token),
    )
    assert response.status_code == 403


FAKE_UUID = "00000000-0000-0000-0000-000000000000"


async def test_profile_by_id_404_when_missing(
    client: AsyncClient, employee_token: str
) -> None:
    response = await client.get(
        f"/api/v1/companies/{FAKE_UUID}/profile",
        headers=_auth(employee_token),
    )
    assert response.status_code == 404


async def test_profile_by_id_distributor_extension_is_returned(
    client: AsyncClient,
    employee_token: str,
    db_session: AsyncSession,
) -> None:
    company = await _make_company(
        db_session, inn="7710000008", company_type="distributor"
    )
    db_session.add(
        Distributor(
            company_id=company.id,
            regions={"list": ["RU-MOW"]},
            brands={"list": ["FAW", "JAC"]},
        )
    )
    await db_session.flush()

    response = await client.get(
        f"/api/v1/companies/{company.id}/profile",
        headers=_auth(employee_token),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["distributor"]["brands"] == {"list": ["FAW", "JAC"]}
