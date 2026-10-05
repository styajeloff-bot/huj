"""Integration tests for the G4 companies additions (list / write / delete)."""
from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.models.companies import Company
from infrastructure.models.users import User

pytestmark = pytest.mark.asyncio


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _seed_company(
    db: AsyncSession,
    *,
    name: str,
    inn: str,
    company_type: str = "dealer",
    is_active: bool = True,
) -> Company:
    c = Company(
        name=name, inn=inn, company_type=company_type, is_active=is_active
    )
    db.add(c)
    await db.flush()
    await db.refresh(c)
    return c


# ---------------------------------------------------------------------------
# GET / list
# ---------------------------------------------------------------------------


async def test_list_companies_unauthenticated_is_401(
    client: AsyncClient,
) -> None:
    response = await client.get("/api/v1/companies")
    assert response.status_code == 401


async def test_list_companies_employee_sees_all(
    client: AsyncClient,
    employee_token: str,
    db_session: AsyncSession,
) -> None:
    a = await _seed_company(db_session, name="Alpha", inn="8100000001")
    b = await _seed_company(db_session, name="Beta", inn="8100000002")

    response = await client.get(
        "/api/v1/companies", headers=_auth(employee_token)
    )
    assert response.status_code == 200
    ids = {item["id"] for item in response.json()["companies"]}
    assert {str(a.id), str(b.id)}.issubset(ids)


async def test_list_companies_client_only_sees_own(
    client: AsyncClient,
    client_token: str,
    client_user: User,
    db_session: AsyncSession,
) -> None:
    mine = await _seed_company(db_session, name="Own", inn="8100000003")
    await _seed_company(db_session, name="Strangers", inn="8100000004")
    client_user.company_id = mine.id
    await db_session.flush()

    response = await client.get(
        "/api/v1/companies", headers=_auth(client_token)
    )
    assert response.status_code == 200
    companies = response.json()["companies"]
    assert [c["id"] for c in companies] == [str(mine.id)]


# ---------------------------------------------------------------------------
# GET /{id}
# ---------------------------------------------------------------------------


async def test_get_company_by_id_employee_ok(
    client: AsyncClient,
    employee_token: str,
    db_session: AsyncSession,
) -> None:
    c = await _seed_company(db_session, name="Foo", inn="8200000001")
    response = await client.get(
        f"/api/v1/companies/{c.id}", headers=_auth(employee_token)
    )
    assert response.status_code == 200
    assert response.json()["id"] == str(c.id)


async def test_get_company_by_id_stranger_is_403(
    client: AsyncClient,
    other_token: str,
    db_session: AsyncSession,
) -> None:
    c = await _seed_company(db_session, name="Mine", inn="8200000002")
    response = await client.get(
        f"/api/v1/companies/{c.id}", headers=_auth(other_token)
    )
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# Phase 15 H3 — /{id}/stats deleted; the aggregate was not used by UI.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# POST /profile (upsert)
# ---------------------------------------------------------------------------


async def test_post_profile_creates_and_attaches(
    client: AsyncClient,
    client_token: str,
    client_user: User,
    db_session: AsyncSession,
) -> None:
    response = await client.post(
        "/api/v1/companies/profile",
        headers=_auth(client_token),
        json={
            "name": "Своя Компания",
            "inn": "8400000001",
            "company_type": "dealer",
            "legal_address": "Россия",
            "phone": "+7-999-000-00-00",
            "email": "new@test.local",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["company_id"] is not None

    await db_session.refresh(client_user)
    assert str(client_user.company_id) == str(body["company_id"])


async def test_post_profile_rejects_invalid_inn(
    client: AsyncClient, client_token: str
) -> None:
    response = await client.post(
        "/api/v1/companies/profile",
        headers=_auth(client_token),
        json={
            "name": "X",
            "inn": "bad",
            "company_type": "dealer",
            "legal_address": "a",
            "phone": "+7",
            "email": "e@e.e",
        },
    )
    assert response.status_code == 422  # pydantic pattern validation


# ---------------------------------------------------------------------------
# PUT /{id}
# ---------------------------------------------------------------------------


async def test_put_company_employee_ok(
    client: AsyncClient,
    employee_token: str,
    db_session: AsyncSession,
) -> None:
    c = await _seed_company(db_session, name="Old", inn="8500000001")
    response = await client.put(
        f"/api/v1/companies/{c.id}",
        headers=_auth(employee_token),
        json={"name": "New"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["company"]["name"] == "New"


async def test_put_company_stranger_is_403(
    client: AsyncClient,
    other_token: str,
    db_session: AsyncSession,
) -> None:
    c = await _seed_company(db_session, name="Guarded", inn="8500000002")
    response = await client.put(
        f"/api/v1/companies/{c.id}",
        headers=_auth(other_token),
        json={"name": "Hack"},
    )
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# PUT /{id}/external-data
# ---------------------------------------------------------------------------


async def test_external_data_update_employee_ok(
    client: AsyncClient,
    employee_token: str,
    db_session: AsyncSession,
) -> None:
    c = await _seed_company(db_session, name="X", inn="8600000001")
    response = await client.put(
        f"/api/v1/companies/{c.id}/external-data",
        headers=_auth(employee_token),
        json={
            "full_name": "ООО «Полное название»",
            "director_full_name": "Иванов И.И.",
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["data"]["full_name"] == "ООО «Полное название»"


# ---------------------------------------------------------------------------
# DELETE /{id}
# ---------------------------------------------------------------------------


async def test_delete_company_employee_soft_deletes(
    client: AsyncClient,
    employee_token: str,
    db_session: AsyncSession,
) -> None:
    c = await _seed_company(db_session, name="Dead", inn="8700000001")
    response = await client.delete(
        f"/api/v1/companies/{c.id}", headers=_auth(employee_token)
    )
    assert response.status_code == 200, response.text
    assert response.json()["company"]["is_active"] is False


async def test_delete_company_non_employee_is_403(
    client: AsyncClient,
    client_token: str,
    db_session: AsyncSession,
) -> None:
    c = await _seed_company(db_session, name="Keep", inn="8700000002")
    response = await client.delete(
        f"/api/v1/companies/{c.id}", headers=_auth(client_token)
    )
    assert response.status_code == 403
