"""Integration tests for /api/v1/admin/applications (Phase 6 — F2)."""
from decimal import Decimal
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.models.applications import (
    ApplicationVehicle,
    LeasingApplication,
    LeasingCompanyApplication,
    LeasingProposal,
)
from infrastructure.models.companies import Company, LeasingCompany

pytestmark = pytest.mark.asyncio


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def company(db_session: AsyncSession) -> Company:
    company = Company(
        name="Admin App Company",
        inn="7799002001",
        company_type="dealer",
        is_active=True,
    )
    db_session.add(company)
    await db_session.flush()
    return company


@pytest_asyncio.fixture
async def leasing_company(db_session: AsyncSession) -> LeasingCompany:
    company = Company(
        name="LC For App",
        inn="7799002002",
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
async def application(
    db_session: AsyncSession, company: Company
) -> LeasingApplication:
    app = LeasingApplication(
        company_id=company.id,
        name="Test Admin App",
        email="adminapp@test.local",
        status="active",
        selected_leasing_companies=[],
        display_number="7799002001-2904-001",
    )
    db_session.add(app)
    await db_session.flush()
    return app


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


async def test_list_applications_happy(
    client: AsyncClient,
    employee_token: str,
    application: LeasingApplication,
) -> None:
    response = await client.get(
        "/api/v1/admin/applications",
        headers=_auth(employee_token),
    )
    assert response.status_code == 200
    body = response.json()
    assert "applications" in body
    assert "pagination" in body
    assert any(
        a["id"] == str(application.id) for a in body["applications"]
    )
    match = next(a for a in body["applications"] if a["id"] == str(application.id))
    assert match["display_number"] == "7799002001-2904-001"


async def test_list_applications_anon_unauthorised(
    client: AsyncClient,
) -> None:
    response = await client.get("/api/v1/admin/applications")
    assert response.status_code == 401


async def test_list_applications_client_forbidden(
    client: AsyncClient, client_token: str
) -> None:
    response = await client.get(
        "/api/v1/admin/applications", headers=_auth(client_token)
    )
    assert response.status_code == 403


async def test_get_application_detail_happy(
    client: AsyncClient,
    employee_token: str,
    application: LeasingApplication,
    leasing_company: LeasingCompany,
    db_session: AsyncSession,
) -> None:
    lca = LeasingCompanyApplication(
        application_id=application.id,
        leasing_company_id=leasing_company.id,
        status="approved_scoring",
    )
    db_session.add(lca)
    await db_session.flush()
    proposal = LeasingProposal(
        leasing_company_application_id=lca.id,
        kind="preliminary",
        position=1,
        total_amount=Decimal("1000000.00"),
        monthly_payment=Decimal("44000.00"),
    )
    db_session.add(proposal)
    await db_session.flush()

    response = await client.get(
        f"/api/v1/admin/applications/{application.id}",
        headers=_auth(employee_token),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["application"]["id"] == str(application.id)
    assert body["leasing_company_applications"][0]["id"] == str(lca.id)
    assert body["leasing_company_applications"][0]["leasing_company"]["name"] == "LC For App"
    assert body["leasing_company_applications"][0]["proposals"][0]["id"] == str(proposal.id)


async def test_get_application_detail_anon_unauthorised(
    client: AsyncClient,
    application: LeasingApplication,
) -> None:
    response = await client.get(f"/api/v1/admin/applications/{application.id}")
    assert response.status_code == 401


async def test_get_application_detail_client_forbidden(
    client: AsyncClient,
    client_token: str,
    application: LeasingApplication,
) -> None:
    response = await client.get(
        f"/api/v1/admin/applications/{application.id}",
        headers=_auth(client_token),
    )
    assert response.status_code == 403


async def test_list_applications_filter_by_status(
    client: AsyncClient,
    employee_token: str,
    application: LeasingApplication,
) -> None:
    response = await client.get(
        "/api/v1/admin/applications?status=active",
        headers=_auth(employee_token),
    )
    assert response.status_code == 200
    assert all(
        a["status"] == "active"
        for a in response.json()["applications"]
    )


# ---------------------------------------------------------------------------
# Assign LCs
# ---------------------------------------------------------------------------


async def test_assign_leasing_companies_happy(
    client: AsyncClient,
    employee_token: str,
    application: LeasingApplication,
    leasing_company: LeasingCompany,
) -> None:
    response = await client.put(
        f"/api/v1/admin/applications/{application.id}/assign-leasing-companies",
        json={"leasing_company_ids": [leasing_company.id]},
        headers=_auth(employee_token),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["assigned_count"] == 1
    assert body["new_links_count"] == 1


async def test_assign_leasing_companies_unknown_lc_404(
    client: AsyncClient,
    employee_token: str,
    application: LeasingApplication,
) -> None:
    response = await client.put(
        f"/api/v1/admin/applications/{application.id}/assign-leasing-companies",
        json={"leasing_company_ids": [str(uuid4())]},
        headers=_auth(employee_token),
    )
    assert response.status_code == 404


async def test_assign_leasing_companies_empty_list_422(
    client: AsyncClient,
    employee_token: str,
    application: LeasingApplication,
) -> None:
    response = await client.put(
        f"/api/v1/admin/applications/{application.id}/assign-leasing-companies",
        json={"leasing_company_ids": []},
        headers=_auth(employee_token),
    )
    assert response.status_code == 422


async def test_assign_leasing_companies_anon_unauthorised(
    client: AsyncClient,
    application: LeasingApplication,
) -> None:
    response = await client.put(
        f"/api/v1/admin/applications/{application.id}/assign-leasing-companies",
        json={"leasing_company_ids": [1]},
    )
    assert response.status_code == 401


async def test_assign_leasing_companies_client_forbidden(
    client: AsyncClient,
    client_token: str,
    application: LeasingApplication,
) -> None:
    response = await client.put(
        f"/api/v1/admin/applications/{application.id}/assign-leasing-companies",
        json={"leasing_company_ids": [1]},
        headers=_auth(client_token),
    )
    assert response.status_code == 403


@pytest.mark.parametrize("quantity", [3, 101])
async def test_admin_card_and_detail_count_vehicle_units(
    client: AsyncClient, employee_token: str, application: LeasingApplication,
    db_session: AsyncSession, quantity: int,
) -> None:
    legacy = ApplicationVehicle(application_id=application.id, unit_price=100, total_price=100)
    db_session.add_all([
        legacy,
        ApplicationVehicle(application_id=application.id, quantity=quantity,
                           unit_price=100, total_price=quantity * 100),
        ApplicationVehicle(application_id=application.id, quantity=2,
                           unit_price=50, total_price=100),
    ])
    await db_session.flush()
    legacy.quantity = None
    await db_session.flush()
    assert legacy.quantity is None
    response = await client.get("/api/v1/admin/applications", headers=_auth(employee_token))
    assert response.status_code == 200
    card = next(item for item in response.json()["applications"] if item["id"] == str(application.id))
    assert card["vehicles_count"] == quantity + 3
    assert Decimal(str(card["total_vehicles_price"])) == quantity * 100 + 200
    detail = await client.get(f"/api/v1/admin/applications/{application.id}", headers=_auth(employee_token))
    assert detail.status_code == 200
    assert detail.json()["application"]["vehicles_count"] == quantity + 3
