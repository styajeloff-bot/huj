"""Integration tests for /api/v1/admin/companies (Phase 6 — F2)."""
from __future__ import annotations

from collections.abc import Iterator

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from domain.values import CompanyInfo
from infrastructure.models.companies import Company
from infrastructure.services.company_lookup import (
    set_company_lookup_provider,
)
from tests.fakes.company_lookup import FakeCompanyLookupProvider

pytestmark = pytest.mark.asyncio


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _make_info() -> CompanyInfo:
    return CompanyInfo(
        name="ООО Админ-Тест",
        full_name="Общество Админ-Тест",
        inn="7799001001",
        kpp=None,
        ogrn=None,
        legal_address="Россия, Москва",
        actual_address=None,
        phone=None,
        email=None,
        foundation_date=None,
        employee_count=None,
        business_activity=None,
        manager_name=None,
        entity_type="LEGAL",
    )


@pytest.fixture(autouse=True)
def _fake_provider() -> Iterator[FakeCompanyLookupProvider]:
    fake = FakeCompanyLookupProvider(items=[_make_info()])
    set_company_lookup_provider(fake)
    yield fake
    set_company_lookup_provider(None)


async def test_create_company_happy_path(
    client: AsyncClient, employee_token: str
) -> None:
    response = await client.post(
        "/api/v1/admin/companies",
        json={"inn": "7799001001", "company_type": "dealer"},
        headers=_auth(employee_token),
    )
    assert response.status_code == 201
    body = response.json()
    assert body["company"]["inn"] == "7799001001"
    assert body["company"]["company_type"] == "dealer"
    assert "Location" in {k.title() for k in response.headers}


async def test_create_company_invalid_inn_returns_422(
    client: AsyncClient, employee_token: str
) -> None:
    response = await client.post(
        "/api/v1/admin/companies",
        json={"inn": "short", "company_type": "dealer"},
        headers=_auth(employee_token),
    )
    assert response.status_code == 422


async def test_create_company_anon_unauthorised(
    client: AsyncClient,
) -> None:
    response = await client.post(
        "/api/v1/admin/companies",
        json={"inn": "7799001001", "company_type": "dealer"},
    )
    assert response.status_code == 401


async def test_create_company_client_forbidden(
    client: AsyncClient, client_token: str
) -> None:
    response = await client.post(
        "/api/v1/admin/companies",
        json={"inn": "7799001001", "company_type": "dealer"},
        headers=_auth(client_token),
    )
    assert response.status_code == 403


async def test_create_company_duplicate_inn_returns_409(
    client: AsyncClient,
    employee_token: str,
    db_session: AsyncSession,
) -> None:
    existing = Company(
        name="Existing Co",
        inn="7799001099",
        company_type="dealer",
        is_active=True,
    )
    db_session.add(existing)
    await db_session.flush()

    response = await client.post(
        "/api/v1/admin/companies",
        json={"inn": "7799001099", "company_type": "dealer"},
        headers=_auth(employee_token),
    )
    assert response.status_code == 409


async def test_create_leasing_company_type(
    client: AsyncClient, employee_token: str
) -> None:
    response = await client.post(
        "/api/v1/admin/companies",
        json={
            "inn": "7799001050",
            "company_type": "leasing_company",
            "name": "LC Direct",
        },
        headers=_auth(employee_token),
    )
    assert response.status_code == 201
    body = response.json()
    assert body["company"]["company_type"] == "leasing_company"
