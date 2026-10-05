"""Integration tests for Phase 7a G5 misc endpoints.

Covers the 10 Express-parity endpoints backported across several
routers:

- GET  /api/v1/admin/applications/{id}/vehicles
- GET  /api/v1/admin/distributors
- GET  /api/v1/admin/warehouses/brands
- GET  /api/v1/leasing/document-requirements
- PUT  /api/v1/leasing/document-requirements
- GET  /api/v1/leasing-applications/{id}
- GET  /api/v1/vehicles/stats/inventory
"""
from __future__ import annotations

from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.auth import generate_tokens
from infrastructure.models.applications import (
    ApplicationVehicle,
    LeasingApplication,
    LeasingApplicationCalculation,
)
from infrastructure.models.companies import (
    Company,
    Distributor,
    LeasingCompany,
)
from infrastructure.models.documents import DocumentType
from infrastructure.models.users import User
from infrastructure.models.vehicles import Warehouse
from tests.legacy_compat import (
    CarModel,
    Configuration,
    Generation,
    Mark,
    Modification,
    Vehicle,
)

pytestmark = pytest.mark.asyncio


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Common fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def g5_company(db_session: AsyncSession) -> Company:
    company = Company(
        name="G5 Customer",
        inn="7799055001",
        company_type="dealer",
        is_active=True,
    )
    db_session.add(company)
    await db_session.flush()
    return company


@pytest_asyncio.fixture
async def g5_leasing_company(db_session: AsyncSession) -> LeasingCompany:
    company = Company(
        name="G5 LC",
        inn="7799055002",
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
async def g5_lc_user(
    db_session: AsyncSession, g5_leasing_company: LeasingCompany
) -> User:
    user = User(
        phone="+76660000001",
        email="lc-g5@test.local",
        name="LC G5 User",
        role="leasing_company",
        is_active=True,
        company_id=g5_leasing_company.company_id,
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


@pytest.fixture
def g5_lc_token(g5_lc_user: User, g5_leasing_company: LeasingCompany) -> str:
    token, _ = generate_tokens(
        g5_lc_user.id,
        "leasing_company",
        g5_leasing_company.company_id,
    )
    return token


@pytest_asyncio.fixture
async def g5_distributor(db_session: AsyncSession) -> Distributor:
    company = Company(
        name="G5 Distributor Inc",
        inn="7799055003",
        company_type="distributor",
        is_active=True,
    )
    db_session.add(company)
    await db_session.flush()
    dist = Distributor(company_id=company.id, is_active=True)
    db_session.add(dist)
    await db_session.flush()
    return dist


@pytest_asyncio.fixture
async def g5_application(
    db_session: AsyncSession,
    g5_company: Company,
    g5_leasing_company: LeasingCompany,
) -> LeasingApplication:
    app = LeasingApplication(
        company_id=g5_company.id,
        name="G5 App",
        email="g5app@test.local",
        status="active",
        selected_leasing_companies=[g5_leasing_company.id],
    )
    db_session.add(app)
    await db_session.flush()
    return app


@pytest_asyncio.fixture
async def g5_application_vehicle(
    db_session: AsyncSession, g5_application: LeasingApplication
) -> ApplicationVehicle:
    av = ApplicationVehicle(
        application_id=g5_application.id,
        quantity=1,
        unit_price=Decimal("1500000.00"),
        total_price=Decimal("1500000.00"),
    )
    db_session.add(av)
    await db_session.flush()
    return av


@pytest_asyncio.fixture
async def g5_warehouse(db_session: AsyncSession) -> Warehouse:
    warehouse = Warehouse(
        address="G5 Test Warehouse Address",
        brand="FAW",
    )
    db_session.add(warehouse)
    await db_session.flush()
    return warehouse


# ---------------------------------------------------------------------------
# Admin: /admin/applications/{id}/vehicles
# ---------------------------------------------------------------------------


async def test_admin_application_vehicles_happy(
    client: AsyncClient,
    employee_token: str,
    g5_application: LeasingApplication,
    g5_application_vehicle: ApplicationVehicle,
) -> None:
    response = await client.get(
        f"/api/v1/admin/applications/{g5_application.id}/vehicles",
        headers=_auth(employee_token),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert "vehicles" in body
    ids = [v["id"] for v in body["vehicles"]]
    assert str(g5_application_vehicle.id) in ids


async def test_admin_application_vehicles_include_catalog_fields(
    client: AsyncClient,
    employee_token: str,
    db_session: AsyncSession,
    g5_application: LeasingApplication,
    default_vehicle_category_id: str,
) -> None:
    mark = Mark(id="G5_FA", name="FAW", cyrillic_name="ФАВ")
    model = CarModel(
        id="G5_T55",
        name="Bestune T55",
        cyrillic_name="Бестюн Т55",
        mark_id=mark.id,
        category=default_vehicle_category_id,
    )
    generation = Generation(id="G5_GEN", model_id=model.id)
    configuration = Configuration(
        id="G5_CFG",
        generation_id=generation.id,
    )
    modification = Modification(
        complectation_id="G5_COMP",
        configuration_id=configuration.id,
        group_name="Comfort",
    )
    vehicle = Vehicle(
        vin="G5VIN00000000001",
        mark_id=mark.id,
        model_id=model.id,
        generation_id=generation.id,
        configuration_id=configuration.id,
        complectation_id=modification.complectation_id,
        year=2023,
        color="Черный",
        status="available",
        base_price=Decimal("1740000.00"),
    )
    db_session.add(mark)
    await db_session.flush()
    db_session.add(model)
    await db_session.flush()
    db_session.add(generation)
    await db_session.flush()
    db_session.add(configuration)
    await db_session.flush()
    db_session.add(modification)
    await db_session.flush()
    db_session.add(vehicle)
    await db_session.flush()
    application_vehicle = ApplicationVehicle(
        application_id=g5_application.id,
        vehicle_id=vehicle.id,
        quantity=1,
        unit_price=Decimal("1740000.00"),
        total_price=Decimal("1740000.00"),
    )
    db_session.add(application_vehicle)
    support_program_id = "5ac82265-7424-4686-a590-9bda1308dffe"
    db_session.add(
        LeasingApplicationCalculation(
            leasing_application_id=g5_application.id,
            support_per_vehicle=[
                {
                    "vehicle_id": str(vehicle.id),
                    "base_price": 1740000,
                    "applied_supports": [
                        {
                            "support_program_id": support_program_id,
                            "type": "vehicle_discount_dealer_compensation",
                            "amount": 87000,
                        }
                    ],
                }
            ],
            support_program_details=[
                {
                    "id": support_program_id,
                    "name": "G5 Dealer Support",
                    "bill_of_lading": None,
                }
            ],
        )
    )
    await db_session.flush()

    response = await client.get(
        f"/api/v1/admin/applications/{g5_application.id}/vehicles",
        headers=_auth(employee_token),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    row = next(v for v in body["vehicles"] if v["id"] == str(application_vehicle.id))
    assert row["mark_name"] == "FAW"
    assert row["mark_cyrillic"] == "ФАВ"
    assert row["model_name"] == "Bestune T55"
    assert row["model_cyrillic"] == "Бестюн Т55"
    assert row["group_name"] == "Comfort"
    assert row["complectation_name"] == "Comfort"
    assert row["color"] == "Черный"
    assert row["year"] == 2023
    assert row["vehicle_year"] == 2023
    assert row["vehicle_vin"] == "G5VIN00000000001"
    assert row["assigned_vin"] is None
    assert row["support_type"] == "vehicle_discount_dealer_compensation"
    assert row["support_amount"] == 87000
    assert row["support_program_id"] == support_program_id
    assert row["support_program_info"]["name"] == "G5 Dealer Support"


async def test_admin_application_vehicles_404(
    client: AsyncClient, employee_token: str
) -> None:
    response = await client.get(
        "/api/v1/admin/applications/a0b1c2d3-e4f5-6789-0123-456789abcdef/vehicles",
        headers=_auth(employee_token),
    )
    assert response.status_code == 404


async def test_admin_application_vehicles_client_forbidden(
    client: AsyncClient,
    client_token: str,
    g5_application: LeasingApplication,
) -> None:
    response = await client.get(
        f"/api/v1/admin/applications/{g5_application.id}/vehicles",
        headers=_auth(client_token),
    )
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# Admin: /admin/distributors
# ---------------------------------------------------------------------------


async def test_admin_distributors_lists_distributor(
    client: AsyncClient,
    employee_token: str,
    g5_distributor: Distributor,
) -> None:
    response = await client.get(
        "/api/v1/admin/distributors", headers=_auth(employee_token)
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert "distributors" in body
    assert any(
        d["id"] == str(g5_distributor.company_id)
        for d in body["distributors"]
    )


async def test_admin_distributors_lists_company_without_extension(
    client: AsyncClient,
    employee_token: str,
    db_session: AsyncSession,
) -> None:
    company = Company(
        name="G5 Distributor Company Only",
        inn="7799055099",
        company_type="distributor",
        is_active=True,
    )
    db_session.add(company)
    await db_session.flush()

    response = await client.get(
        "/api/v1/admin/distributors", headers=_auth(employee_token)
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert any(
        d["id"] == str(company.id)
        and d["company_id"] == str(company.id)
        and d["name"] == company.name
        for d in body["distributors"]
    )


async def test_admin_distributors_client_forbidden(
    client: AsyncClient, client_token: str
) -> None:
    response = await client.get(
        "/api/v1/admin/distributors", headers=_auth(client_token)
    )
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# Admin: /admin/warehouses/brands (was /admin/warehouses-brands; Phase 11 R9)
# ---------------------------------------------------------------------------


async def test_admin_warehouses_brands_happy(
    client: AsyncClient,
    employee_token: str,
    g5_warehouse: Warehouse,
) -> None:
    response = await client.get(
        "/api/v1/admin/warehouses/brands",
        headers=_auth(employee_token),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert "brands" in body
    assert g5_warehouse.brand in body["brands"]


async def test_admin_warehouses_brands_client_forbidden(
    client: AsyncClient, client_token: str
) -> None:
    response = await client.get(
        "/api/v1/admin/warehouses/brands",
        headers=_auth(client_token),
    )
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# (Phase 15 H3) — /application-documents/pending-reviews deleted; no
# frontend caller. Upload shim (Phase 10 R4) was also removed earlier;
# document uploads now go through `POST /documents` with `application_id`.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Leasing: /document-requirements aliases
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def g5_document_type(db_session: AsyncSession) -> DocumentType:
    dt = DocumentType(
        name="Test DocType",
        type_code="g5_doctype",
        display_name="Тестовый тип",
    )
    db_session.add(dt)
    await db_session.flush()
    return dt


async def test_leasing_document_requirements_get_happy(
    client: AsyncClient,
    g5_lc_token: str,
    g5_leasing_company: LeasingCompany,
) -> None:
    response = await client.get(
        "/api/v1/leasing/document-requirements",
        headers=_auth(g5_lc_token),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert "leasing_company" in body
    assert "requirements" in body


async def test_leasing_document_requirements_put_happy(
    client: AsyncClient,
    g5_lc_token: str,
    g5_leasing_company: LeasingCompany,
    g5_document_type: DocumentType,
) -> None:
    response = await client.put(
        "/api/v1/leasing/document-requirements",
        headers=_auth(g5_lc_token),
        json={
            "requirements": [
                {
                    "document_type_id": g5_document_type.id,
                    "is_required": True,
                    "is_mandatory": True,
                    "sort_order": 1,
                }
            ]
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["leasing_company_id"] == str(g5_leasing_company.id)
    assert body["updated_count"] == 1


async def test_leasing_document_requirements_get_forbidden_for_client(
    client: AsyncClient, client_token: str
) -> None:
    response = await client.get(
        "/api/v1/leasing/document-requirements",
        headers=_auth(client_token),
    )
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# Leasing-applications: GET /{id}
# ---------------------------------------------------------------------------





# ---------------------------------------------------------------------------
# Vehicles: /stats/inventory
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def g5_vehicle(db_session: AsyncSession) -> Vehicle:
    vehicle = Vehicle(
        status="available",
        is_available=True,
        base_price=Decimal("1000000.00"),
    )
    db_session.add(vehicle)
    await db_session.flush()
    await db_session.refresh(vehicle)
    return vehicle


