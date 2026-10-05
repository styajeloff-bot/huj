from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.models.companies import Company, LeasingCompany
from infrastructure.services.excel_io import write_workbook

pytestmark = pytest.mark.asyncio


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def leasing_company(db_session: AsyncSession) -> LeasingCompany:
    company = Company(
        name="Router LC",
        inn="7799004001",
        company_type="leasing_company",
        is_active=True,
    )
    db_session.add(company)
    await db_session.flush()
    lc = LeasingCompany(company_id=company.id, is_active=True)
    db_session.add(lc)
    await db_session.flush()
    return lc


async def test_contractors_auth_enforced(
    client: AsyncClient, client_token: str
) -> None:
    anon = await client.get("/api/v1/admin/companies/contractors")
    assert anon.status_code == 401

    forbidden = await client.get(
        "/api/v1/admin/companies/contractors",
        headers=_auth(client_token),
    )
    assert forbidden.status_code == 403


async def test_contractors_crud_flow(
    client: AsyncClient,
    employee_token: str,
    leasing_company: LeasingCompany,
) -> None:
    create = await client.post(
        "/api/v1/admin/companies/contractors",
        json={
            "contractor_name": "АО ОКБ",
            "contractor_inn": "770 123-45-67",
        },
        headers=_auth(employee_token),
    )
    assert create.status_code == 201
    created = create.json()
    assert created["created"] is True
    assert created["contractor"]["inn"] == "7701234567"

    list_response = await client.get(
        "/api/v1/admin/companies/contractors?inn=7701234567",
        headers=_auth(employee_token),
    )
    assert list_response.status_code == 200
    body = list_response.json()
    assert body["pagination"]["total"] == 1
    assert body["items"][0]["inn"] == "7701234567"

    contractor_id = created["contractor"]["id"]
    link_response = await client.put(
        f"/api/v1/admin/companies/leasing-companies/{leasing_company.id}/contractors",
        json={"contractor_ids": [contractor_id]},
        headers=_auth(employee_token),
    )
    assert link_response.status_code == 200
    link_body = link_response.json()
    assert len(link_body["items"]) == 1
    assert link_body["items"][0]["contractor_id"] == contractor_id

    reverse_links = await client.get(
        f"/api/v1/admin/companies/contractors/{contractor_id}/leasing-companies",
        headers=_auth(employee_token),
    )
    assert reverse_links.status_code == 200
    assert reverse_links.json()["items"][0]["leasing_company_id"] == str(
        leasing_company.id
    )

    update = await client.patch(
        f"/api/v1/admin/companies/contractors/{contractor_id}",
        json={"name": "АО Объединённое кредитное бюро"},
        headers=_auth(employee_token),
    )
    assert update.status_code == 200
    assert update.json()["contractor"]["name"] == "АО Объединённое кредитное бюро"

    unlink = await client.put(
        f"/api/v1/admin/companies/leasing-companies/{leasing_company.id}/contractors",
        json={"contractor_ids": []},
        headers=_auth(employee_token),
    )
    assert unlink.status_code == 200
    assert unlink.json()["items"] == []

    catalog = await client.get(
        "/api/v1/admin/companies/contractors?inn=7701234567",
        headers=_auth(employee_token),
    )
    assert catalog.status_code == 200
    assert catalog.json()["pagination"]["total"] == 1


async def test_contractors_import_endpoint_reports_row_errors(
    client: AsyncClient,
    employee_token: str,
    leasing_company: LeasingCompany,
) -> None:
    headers = ["leasing_company_inn", "contractor_name", "contractor_inn"]
    data = await write_workbook(
        headers,
        [
            ["7799004001", "АО ОКБ", "7701234567"],
            ["7799004001", "АО ОКБ", "7701234567"],
            ["7799004099", "ООО Нет ЛК", "7700000001"],
            ["7799004001", "ООО Ошибка", "bad-inn"],
        ],
        sheet_name="contractors",
    )

    response = await client.post(
        "/api/v1/admin/companies/contractors/import",
        files={
            "file": (
                "contractors.xlsx",
                data,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
        headers=_auth(employee_token),
    )

    assert leasing_company.id
    assert response.status_code == 200
    body = response.json()
    assert body["rows_total"] == 4
    assert body["links_created"] == 1
    assert body["links_skipped"] == 1
    assert body["contractors_created"] == 1
    assert len(body["errors"]) == 2
    assert body["errors"][0]["row"] == 4
    assert body["errors"][1]["row"] == 5
    assert "ИНН должен содержать" in body["errors"][1]["message"]
