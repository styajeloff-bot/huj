"""Integration tests for /api/v1/distributor (B3)."""

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
    LeasingApplicationVehicleCalculation,
)
from infrastructure.models.companies import (
    Company,
    Distributor,
    DistributorBrand,
    DistributorDealerLink,
    LeasingCompany,
)
from infrastructure.models.compensations import CompensationTemplateModel
from infrastructure.models.support import (
    DealerGroup,
    DealerGroupMember,
    SupportProgram,
    SupportProgramDistributor,
    SupportProgramLeasingCompany,
)
from infrastructure.models.users import User, UserCompany
from infrastructure.models.vehicles import Warehouse
from infrastructure.services.excel_io import write_workbook
from tests.legacy_compat import CarModel, Mark, Vehicle, VehicleWarehouse

pytestmark = pytest.mark.asyncio


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def distributor_company(db_session: AsyncSession) -> Company:
    company = Company(
        name="Distributor Co",
        company_type="distributor",
        inn="9999999999",
    )
    db_session.add(company)
    await db_session.flush()
    return company


@pytest_asyncio.fixture
async def distributor_row(
    db_session: AsyncSession, distributor_company: Company
) -> Distributor:
    row = Distributor(company_id=distributor_company.id, is_active=True)
    db_session.add(row)
    await db_session.flush()
    return row


@pytest_asyncio.fixture
async def distributor_user(
    db_session: AsyncSession,
    distributor_company: Company,
    linked_dealer_company: Company,
    distributor_row: Distributor,
) -> User:
    user = User(
        phone="+76660000001",
        email="dist@test.local",
        name="Distributor User",
        role="distributor",
        company_id=distributor_company.id,
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


@pytest.fixture
def distributor_token(distributor_user: User) -> str:
    token, _ = generate_tokens(
        distributor_user.id, "distributor", distributor_user.company_id
    )
    return token


@pytest_asyncio.fixture
async def foreign_dealer(db_session: AsyncSession) -> User:
    """A dealer user that is NOT the distributor — used as the owner of
    out-of-scope vehicles in scope-isolation tests. Backed by a real row
    so the vehicles_dealer_id_fkey FK is satisfied."""
    user = User(
        phone="+76660000099",
        email="foreign-dealer@test.local",
        name="Foreign Dealer",
        role="dealer",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def foreign_dealer_company(db_session: AsyncSession) -> Company:
    company = Company(
        name="Foreign Dealer Company",
        company_type="dealer",
        is_active=True,
    )
    db_session.add(company)
    await db_session.flush()
    return company


@pytest_asyncio.fixture
async def linked_dealer_company(db_session: AsyncSession) -> Company:
    company = Company(
        name="Linked Dealer Company",
        company_type="dealer",
        is_active=True,
    )
    db_session.add(company)
    await db_session.flush()
    return company


@pytest_asyncio.fixture
async def linked_dealer_user(
    db_session: AsyncSession,
    linked_dealer_company: Company,
) -> User:
    user = User(
        phone="+76660000002",
        email="linked-dealer@test.local",
        name="Linked Dealer User",
        role="dealer",
        company_id=linked_dealer_company.id,
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    db_session.add(
        UserCompany(
            user_id=user.id,
            company_id=linked_dealer_company.id,
            sub_role="administrator",
            can_view_applications=True,
            can_create_applications=True,
        )
    )
    await db_session.flush()
    await db_session.refresh(user)
    return user


@pytest.fixture
def linked_dealer_token(linked_dealer_user: User) -> str:
    token, _ = generate_tokens(
        linked_dealer_user.id,
        "dealer",
        linked_dealer_user.company_id,
    )
    return token


@pytest_asyncio.fixture
async def foreign_dealer_user(
    db_session: AsyncSession,
    foreign_dealer_company: Company,
) -> User:
    user = User(
        phone="+76660000003",
        email="foreign-company-dealer@test.local",
        name="Foreign Company Dealer User",
        role="dealer",
        company_id=foreign_dealer_company.id,
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    db_session.add(
        UserCompany(
            user_id=user.id,
            company_id=foreign_dealer_company.id,
            sub_role="administrator",
            can_view_applications=True,
            can_create_applications=True,
        )
    )
    await db_session.flush()
    await db_session.refresh(user)
    return user


@pytest.fixture
def foreign_dealer_token(foreign_dealer_user: User) -> str:
    token, _ = generate_tokens(
        foreign_dealer_user.id,
        "dealer",
        foreign_dealer_user.company_id,
    )
    return token


@pytest_asyncio.fixture(autouse=True)
async def distributor_dealer_link(
    db_session: AsyncSession,
    distributor_company: Company,
    linked_dealer_company: Company,
) -> DistributorDealerLink:
    link = DistributorDealerLink(
        distributor_company_id=distributor_company.id,
        dealer_company_id=linked_dealer_company.id,
    )
    db_session.add(link)
    await db_session.flush()
    return link


@pytest_asyncio.fixture
async def mark_bmw(db_session: AsyncSession) -> Mark:
    mark = Mark(id="bmw_dist", name="BMW")
    db_session.add(mark)
    await db_session.flush()
    return mark


@pytest_asyncio.fixture
async def distributor_application_scope(
    db_session: AsyncSession, distributor_user: User, distributor_company: Company,
    linked_dealer_company: Company, mark_bmw: Mark,
) -> None:
    group = DealerGroup(distributor_company_id=distributor_company.id,
        name="Application dealers", is_active=True, created_by=distributor_user.id)
    db_session.add(group)
    await db_session.flush()
    db_session.add_all([
        DealerGroupMember(dealer_group_id=group.id, dealer_company_id=linked_dealer_company.id,
                          created_by=distributor_user.id),
        DistributorBrand(distributor_company_id=distributor_company.id, brand_id=mark_bmw.id),
    ])
    await db_session.flush()


async def _bind_application_stock(db_session: AsyncSession, vehicle: Vehicle, company: Company) -> None:
    warehouse = Warehouse(company_id=company.id, address="Application stock", brand="BMW")
    db_session.add(warehouse)
    await db_session.flush()
    db_session.add(VehicleWarehouse(vehicle_id=vehicle.id, warehouse_id=warehouse.id))
    await db_session.flush()


@pytest_asyncio.fixture
async def model_x5(
    db_session: AsyncSession,
    mark_bmw: Mark,
    default_vehicle_category_id: str,
) -> CarModel:
    model = CarModel(
        id="x5_dist",
        name="X5",
        mark_id=mark_bmw.id,
        category=default_vehicle_category_id,
    )
    db_session.add(model)
    await db_session.flush()
    return model


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


async def test_listing_anonymous_is_unauthorised(client: AsyncClient) -> None:
    response = await client.get("/api/v1/distributor/vehicles")
    assert response.status_code == 401


async def test_listing_client_is_forbidden(
    client: AsyncClient, client_token: str
) -> None:
    response = await client.get(
        "/api/v1/distributor/vehicles", headers=_auth(client_token)
    )
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# CRUD golden path (distributor user)
# ---------------------------------------------------------------------------


async def test_create_and_list_vehicle(
    client: AsyncClient,
    distributor_token: str,
    distributor_user: User,
    distributor_company: Company,
    linked_dealer_company: Company,
    mark_bmw: Mark,
    model_x5: CarModel,
) -> None:
    create = await client.post(
        "/api/v1/distributor/vehicles",
        json={
            "vin": "DISTVIN0000001",
            "mark_id": mark_bmw.id,
            "model_id": model_x5.id,
            "year": 2024,
            "base_price": "5000000.00",
        },
        headers=_auth(distributor_token),
    )
    assert create.status_code == 201, create.text
    body = create.json()
    assert body["vehicle"]["vin"] == "DISTVIN0000001"
    # dealer_id defaults to the only linked dealer in the distributor scope.
    assert body["vehicle"]["dealer_id"] == str(linked_dealer_company.id)

    listing = await client.get(
        "/api/v1/distributor/vehicles",
        headers=_auth(distributor_token),
    )
    assert listing.status_code == 200
    items = listing.json()["vehicles"]
    assert any(v["vin"] == "DISTVIN0000001" for v in items)


async def test_distributor_listing_is_scoped(
    client: AsyncClient,
    db_session: AsyncSession,
    distributor_token: str,
    distributor_company: Company,
    linked_dealer_company: Company,
    foreign_dealer_company: Company,
    mark_bmw: Mark,
) -> None:
    # Vehicle owned by another company — must not surface in distributor scope.
    other = Vehicle(
        mark_id=mark_bmw.id,
        vin="OUTOFSCOPE001",
        status="available",
        dealer_id=foreign_dealer_company.id,
    )
    own = Vehicle(
        mark_id=mark_bmw.id,
        vin="INSCOPE000001",
        status="available",
        dealer_id=linked_dealer_company.id,
    )
    db_session.add_all([other, own])
    await db_session.flush()

    response = await client.get(
        "/api/v1/distributor/vehicles",
        headers=_auth(distributor_token),
    )
    assert response.status_code == 200
    vins = {v["vin"] for v in response.json()["vehicles"]}
    assert "INSCOPE000001" in vins
    assert "OUTOFSCOPE001" not in vins


async def test_update_vehicle_in_scope(
    client: AsyncClient,
    db_session: AsyncSession,
    distributor_token: str,
    distributor_company: Company,
    linked_dealer_company: Company,
    mark_bmw: Mark,
    model_x5: CarModel,
) -> None:
    own = Vehicle(
        mark_id=mark_bmw.id,
        model_id=model_x5.id,
        status="available",
        dealer_id=linked_dealer_company.id,
        base_price=Decimal("1000000.00"),
    )
    db_session.add(own)
    await db_session.flush()

    response = await client.put(
        f"/api/v1/distributor/vehicles/{own.id}",
        json={"status": "reserved", "base_price": "1100000.00"},
        headers=_auth(distributor_token),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["vehicle"]["status"] == "reserved"


async def test_update_foreign_vehicle_is_forbidden(
    client: AsyncClient,
    db_session: AsyncSession,
    distributor_token: str,
    distributor_user: User,
    foreign_dealer_company: Company,
    mark_bmw: Mark,
    model_x5: CarModel,
) -> None:
    foreign = Vehicle(
        mark_id=mark_bmw.id,
        model_id=model_x5.id,
        status="available",
        dealer_id=foreign_dealer_company.id,
    )
    db_session.add(foreign)
    await db_session.flush()

    response = await client.put(
        f"/api/v1/distributor/vehicles/{foreign.id}",
        json={"status": "reserved"},
        headers=_auth(distributor_token),
    )
    assert response.status_code == 403


# VIN assignment was consolidated into PATCH /api/v1/application-vehicles/{id}
# (Phase 13 R13c). See tests/integration/test_application_vehicles_router.py
# for coverage. The distributor-scoped PUT /vehicles/{id}/vin was removed in
# Phase 15 H2.


# ---------------------------------------------------------------------------
# Bulk operations
# ---------------------------------------------------------------------------


async def test_bulk_update_status_in_scope(
    client: AsyncClient,
    db_session: AsyncSession,
    distributor_token: str,
    distributor_company: Company,
    linked_dealer_company: Company,
    mark_bmw: Mark,
    model_x5: CarModel,
) -> None:
    v1 = Vehicle(
        mark_id=mark_bmw.id,
        model_id=model_x5.id,
        status="available",
        dealer_id=linked_dealer_company.id,
    )
    v2 = Vehicle(
        mark_id=mark_bmw.id,
        model_id=model_x5.id,
        status="available",
        dealer_id=linked_dealer_company.id,
    )
    db_session.add_all([v1, v2])
    await db_session.flush()

    response = await client.patch(
        "/api/v1/distributor/vehicles",
        json={
            "ids": [v1.id, v2.id],
            "patch": {"status": "reserved"},
        },
        headers=_auth(distributor_token),
    )
    assert response.status_code == 200, response.text
    assert response.json()["updated_count"] == 2


async def test_bulk_update_blocks_out_of_scope(
    client: AsyncClient,
    db_session: AsyncSession,
    distributor_token: str,
    distributor_company: Company,
    linked_dealer_company: Company,
    foreign_dealer_company: Company,
    mark_bmw: Mark,
) -> None:
    own = Vehicle(
        mark_id=mark_bmw.id,
        status="available",
        dealer_id=linked_dealer_company.id,
    )
    foreign = Vehicle(
        mark_id=mark_bmw.id,
        status="available",
        dealer_id=foreign_dealer_company.id,
    )
    db_session.add_all([own, foreign])
    await db_session.flush()

    response = await client.patch(
        "/api/v1/distributor/vehicles",
        json={
            "ids": [own.id, foreign.id],
            "patch": {"status": "reserved"},
        },
        headers=_auth(distributor_token),
    )
    assert response.status_code == 403


async def test_bulk_import_endpoint_happy_path(
    client: AsyncClient,
    db_session: AsyncSession,
    distributor_token: str,
    mark_bmw: Mark,
    model_x5: CarModel,
) -> None:
    headers = ["VIN", "Марка", "Модель", "Год", "Базовая цена", "Статус"]
    rows = [
        ["IMPVIN0000001", "BMW", "X5", 2024, 5000000, "В наличии"],
        ["IMPVIN0000002", "BMW", "X5", 2024, 5500000, "В наличии"],
        # missing VIN — collected as a row error, not a 4xx
        ["", "BMW", "X5", 2024, 5000000, "В наличии"],
    ]
    file_bytes = await write_workbook(headers, rows)

    response = await client.post(
        "/api/v1/distributor/vehicles/import",
        files={
            "file": (
                "vehicles.xlsx",
                file_bytes,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
        headers=_auth(distributor_token),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["imported"] == 2
    assert body["total_rows"] == 3
    assert len(body["errors"]) == 1
    assert body["errors"][0]["row"] == 4  # 1-indexed + header


async def test_bulk_import_rejects_non_excel(
    client: AsyncClient, distributor_token: str
) -> None:
    response = await client.post(
        "/api/v1/distributor/vehicles/import",
        files={"file": ("vehicles.csv", b"a,b,c", "text/csv")},
        headers=_auth(distributor_token),
    )
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# Applications
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("distributor_application_scope")
async def test_applications_listing_scoped(
    client: AsyncClient,
    db_session: AsyncSession,
    distributor_token: str,
    distributor_user: User,
    foreign_dealer_company: Company,
    distributor_company: Company,
    linked_dealer_company: Company,
    mark_bmw: Mark,
) -> None:
    own_vehicle = Vehicle(
        mark_id=mark_bmw.id,
        status="available",
        dealer_id=linked_dealer_company.id,
    )
    foreign_vehicle = Vehicle(
        mark_id=mark_bmw.id,
        status="available",
        dealer_id=foreign_dealer_company.id,
    )
    db_session.add_all([own_vehicle, foreign_vehicle])
    await db_session.flush()
    await _bind_application_stock(db_session, own_vehicle, linked_dealer_company)

    own_app = LeasingApplication(company_id=distributor_company.id, status="active")
    foreign_app = LeasingApplication(company_id=distributor_company.id, status="active")
    db_session.add_all([own_app, foreign_app])
    await db_session.flush()

    db_session.add_all(
        [
            ApplicationVehicle(
                application_id=own_app.id,
                vehicle_id=own_vehicle.id,
                quantity=1,
            ),
            ApplicationVehicle(
                application_id=foreign_app.id,
                vehicle_id=foreign_vehicle.id,
                quantity=1,
            ),
        ]
    )
    await db_session.flush()

    response = await client.get(
        "/api/v1/distributor/applications",
        headers=_auth(distributor_token),
    )
    assert response.status_code == 200, response.text
    ids = {a["id"] for a in response.json()["applications"]}
    assert str(own_app.id) in ids
    assert str(foreign_app.id) not in ids


async def test_distributor_application_vehicles_returns_404_for_foreign_application(
    client: AsyncClient,
    db_session: AsyncSession,
    distributor_token: str,
    distributor_company: Company,
    foreign_dealer_company: Company,
    mark_bmw: Mark,
) -> None:
    foreign_vehicle = Vehicle(
        mark_id=mark_bmw.id,
        status="available",
        dealer_id=foreign_dealer_company.id,
    )
    db_session.add(foreign_vehicle)
    await db_session.flush()
    foreign_application = LeasingApplication(
        company_id=distributor_company.id, status="active"
    )
    db_session.add(foreign_application)
    await db_session.flush()
    db_session.add(
        ApplicationVehicle(
            application_id=foreign_application.id,
            vehicle_id=foreign_vehicle.id,
            quantity=1,
        )
    )
    await db_session.flush()

    response = await client.get(
        f"/api/v1/distributor/applications/{foreign_application.id}/vehicles",
        headers=_auth(distributor_token),
    )
    assert response.status_code == 404


@pytest.mark.usefixtures("distributor_application_scope")
async def test_general_applications_api_is_scoped_for_distributor(
    client: AsyncClient,
    db_session: AsyncSession,
    distributor_token: str,
    distributor_company: Company,
    linked_dealer_company: Company,
    foreign_dealer_company: Company,
    mark_bmw: Mark,
) -> None:
    own_vehicle = Vehicle(
        mark_id=mark_bmw.id, status="available", dealer_id=linked_dealer_company.id
    )
    foreign_vehicle = Vehicle(
        mark_id=mark_bmw.id, status="available", dealer_id=foreign_dealer_company.id
    )
    db_session.add_all([own_vehicle, foreign_vehicle])
    await db_session.flush()
    await _bind_application_stock(db_session, own_vehicle, linked_dealer_company)
    own_application = LeasingApplication(
        company_id=distributor_company.id, status="active"
    )
    foreign_application = LeasingApplication(
        company_id=distributor_company.id, status="active"
    )
    db_session.add_all([own_application, foreign_application])
    await db_session.flush()
    db_session.add_all(
        [
            ApplicationVehicle(
                application_id=own_application.id, vehicle_id=own_vehicle.id, quantity=1
            ),
            ApplicationVehicle(
                application_id=foreign_application.id,
                vehicle_id=foreign_vehicle.id,
                quantity=1,
            ),
        ]
    )
    await db_session.flush()

    listing = await client.get("/api/v1/applications", headers=_auth(distributor_token))
    assert listing.status_code == 200, listing.text
    application_ids = {item["id"] for item in listing.json()["applications"]}
    assert str(own_application.id) in application_ids
    assert str(foreign_application.id) not in application_ids
    assert listing.json()["total"] == 1

    own_detail = await client.get(
        f"/api/v1/applications/{own_application.id}",
        headers=_auth(distributor_token),
    )
    assert own_detail.status_code == 200, own_detail.text
    assert [item["item_id"] for item in own_detail.json()["items"]] == [
        str(own_vehicle.id)
    ]

    foreign_detail = await client.get(
        f"/api/v1/applications/{foreign_application.id}",
        headers=_auth(distributor_token),
    )
    assert foreign_detail.status_code == 404


@pytest_asyncio.fixture
async def mixed_dealer_application(
    db_session: AsyncSession,
    distributor_company: Company,
    linked_dealer_company: Company,
    foreign_dealer_company: Company,
    mark_bmw: Mark,
) -> tuple[
    LeasingApplication,
    Vehicle,
    Vehicle,
    ApplicationVehicle,
    ApplicationVehicle,
]:
    foreign_mark = Mark(id="faw_mixed_dist", name="FAW")
    linked_vehicle = Vehicle(
        mark_id=mark_bmw.id,
        status="available",
        dealer_id=linked_dealer_company.id,
    )
    foreign_vehicle = Vehicle(
        mark_id=foreign_mark.id,
        status="available",
        dealer_id=foreign_dealer_company.id,
    )
    db_session.add_all([foreign_mark, linked_vehicle, foreign_vehicle])
    await db_session.flush()
    await _bind_application_stock(db_session, linked_vehicle, linked_dealer_company)
    await _bind_application_stock(db_session, foreign_vehicle, foreign_dealer_company)

    application = LeasingApplication(
        company_id=distributor_company.id,
        status="active",
        total_amount=Decimal("5480000.00"),
        down_payment=Decimal("1096000.00"),
        monthly_payment=Decimal("150000.00"),
        total_cost=Decimal("6000000.00"),
    )
    db_session.add(application)
    await db_session.flush()

    linked_line = ApplicationVehicle(
        application_id=application.id,
        vehicle_id=linked_vehicle.id,
        quantity=2,
        unit_price=Decimal("1870000.00"),
        total_price=Decimal("3740000.00"),
    )
    foreign_line = ApplicationVehicle(
        application_id=application.id,
        vehicle_id=foreign_vehicle.id,
        quantity=1,
        unit_price=Decimal("1740000.00"),
        total_price=Decimal("1740000.00"),
    )
    db_session.add_all([linked_line, foreign_line])
    await db_session.flush()

    db_session.add_all(
        [
            LeasingApplicationCalculation(
                leasing_application_id=application.id,
                monthly_payment=Decimal("150000.00"),
                rate=Decimal("12.5000"),
                total_cost=Decimal("6000000.00"),
                total_interest=Decimal("520000.00"),
                base_total=Decimal("5480000.00"),
                vehicle_discount_support=Decimal("100000.00"),
                effective_total=Decimal("5480000.00"),
                selected_support={
                    str(linked_vehicle.id): ["linked-program"],
                    str(foreign_vehicle.id): ["foreign-program"],
                },
                support_per_vehicle=[
                    {
                        "vehicle_id": str(linked_vehicle.id),
                        "base_price": 3740000,
                    },
                    {
                        "vehicle_id": str(foreign_vehicle.id),
                        "base_price": 1740000,
                    },
                ],
                calculations_per_vehicle=[
                    {
                        "vehicle_id": str(linked_vehicle.id),
                        "calculation": {"monthlyPayment": 100000},
                    },
                    {
                        "vehicle_id": str(foreign_vehicle.id),
                        "calculation": {"monthlyPayment": 50000},
                    },
                ],
                support_per_program=[
                    {
                        "support_program_id": "foreign-program",
                        "totals": {"amount": 100000},
                    }
                ],
                support_program_details=[{"id": "foreign-program"}],
            ),
            LeasingApplicationVehicleCalculation(
                leasing_application_id=application.id,
                vehicle_id=linked_vehicle.id,
                quantity=2,
                unit_price=Decimal("1870000.00"),
                total_amount=Decimal("3740000.00"),
                sort_order=0,
            ),
            LeasingApplicationVehicleCalculation(
                leasing_application_id=application.id,
                vehicle_id=foreign_vehicle.id,
                quantity=1,
                unit_price=Decimal("1740000.00"),
                total_amount=Decimal("1740000.00"),
                sort_order=1,
            ),
        ]
    )
    await db_session.flush()

    return application, linked_vehicle, foreign_vehicle, linked_line, foreign_line


async def _assert_mixed_application_scoped_for_dealer(
    client: AsyncClient,
    token: str,
    *,
    application: LeasingApplication,
    expected_vehicle: Vehicle,
    expected_line: ApplicationVehicle,
    expected_title: str,
    expected_quantity: int,
    expected_total: Decimal,
    expected_program: str,
) -> None:
    listing = await client.get(
        "/api/v1/applications",
        headers=_auth(token),
    )
    assert listing.status_code == 200, listing.text
    listed = next(
        item
        for item in listing.json()["applications"]
        if item["id"] == str(application.id)
    )
    assert [item["id"] for item in listed["items"]] == [str(expected_line.id)]
    assert [item["item_id"] for item in listed["items"]] == [
        str(expected_vehicle.id)
    ]
    assert [item["title"] for item in listed["items"]] == [expected_title]
    assert listed["vehicles_count"] == expected_quantity
    assert listed["items_count"] == expected_quantity
    assert Decimal(str(listed["total_amount"])) == expected_total
    assert Decimal(str(listed["total_vehicles_price"])) == expected_total
    assert Decimal(str(listed["total_items_price"])) == expected_total
    for field_name in ("down_payment", "monthly_payment", "total_cost"):
        assert listed[field_name] is None

    detail = await client.get(
        f"/api/v1/applications/{application.id}",
        headers=_auth(token),
    )
    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert [item["id"] for item in body["items"]] == [str(expected_line.id)]
    assert [item["item_id"] for item in body["items"]] == [
        str(expected_vehicle.id)
    ]
    assert [item["title"] for item in body["items"]] == [expected_title]
    assert [vehicle["id"] for vehicle in body["vehicles"]] == [
        str(expected_line.id)
    ]
    assert [vehicle["vehicle_id"] for vehicle in body["vehicles"]] == [
        str(expected_vehicle.id)
    ]
    assert body["vehicles_count"] == expected_quantity
    assert body["items_count"] == expected_quantity
    assert Decimal(str(body["total_amount"])) == expected_total
    assert Decimal(str(body["total_vehicles_price"])) == expected_total
    assert Decimal(str(body["total_items_price"])) == expected_total
    assert [row["vehicle_id"] for row in body["vehicle_calculations"]] == [
        str(expected_vehicle.id)
    ]
    for field_name in ("down_payment", "monthly_payment", "total_cost"):
        assert body[field_name] is None
    calculation = body["calculation"]
    assert Decimal(str(calculation["base_total"])) == expected_total
    for field_name in (
        "monthly_payment",
        "rate",
        "total_cost",
        "total_interest",
        "vehicle_discount_support",
        "effective_total",
    ):
        assert calculation[field_name] is None
    assert [
        row["vehicle_id"] for row in calculation["calculations_per_vehicle"]
    ] == [str(expected_vehicle.id)]
    assert [
        row["vehicle_id"] for row in calculation["support_per_vehicle"]
    ] == [str(expected_vehicle.id)]
    assert calculation["selected_support"] == {
        str(expected_vehicle.id): [expected_program]
    }
    assert calculation["support_per_program"] == []
    assert calculation["support_program_details"] == []


async def test_general_applications_api_scopes_mixed_application_children_for_linked_dealer(
    client: AsyncClient,
    linked_dealer_token: str,
    mixed_dealer_application: tuple[
        LeasingApplication,
        Vehicle,
        Vehicle,
        ApplicationVehicle,
        ApplicationVehicle,
    ],
) -> None:
    application, linked_vehicle, _, linked_line, _ = mixed_dealer_application

    await _assert_mixed_application_scoped_for_dealer(
        client,
        linked_dealer_token,
        application=application,
        expected_vehicle=linked_vehicle,
        expected_line=linked_line,
        expected_title="BMW",
        expected_quantity=2,
        expected_total=Decimal("3740000.00"),
        expected_program="linked-program",
    )


async def test_general_applications_api_scopes_mixed_application_children_for_foreign_dealer(
    client: AsyncClient,
    foreign_dealer_token: str,
    mixed_dealer_application: tuple[
        LeasingApplication,
        Vehicle,
        Vehicle,
        ApplicationVehicle,
        ApplicationVehicle,
    ],
) -> None:
    application, _, foreign_vehicle, _, foreign_line = mixed_dealer_application

    await _assert_mixed_application_scoped_for_dealer(
        client,
        foreign_dealer_token,
        application=application,
        expected_vehicle=foreign_vehicle,
        expected_line=foreign_line,
        expected_title="FAW",
        expected_quantity=1,
        expected_total=Decimal("1740000.00"),
        expected_program="foreign-program",
    )


@pytest.mark.usefixtures("distributor_application_scope")
async def test_general_applications_api_scopes_mixed_application_children_for_distributor(
    client: AsyncClient,
    distributor_token: str,
    mixed_dealer_application: tuple[
        LeasingApplication,
        Vehicle,
        Vehicle,
        ApplicationVehicle,
        ApplicationVehicle,
    ],
) -> None:
    application, linked_vehicle, foreign_vehicle, linked_line, _ = (
        mixed_dealer_application
    )

    listing = await client.get(
        "/api/v1/applications",
        headers=_auth(distributor_token),
    )
    assert listing.status_code == 200, listing.text
    listed = next(
        item
        for item in listing.json()["applications"]
        if item["id"] == str(application.id)
    )
    assert [item["id"] for item in listed["items"]] == [str(linked_line.id)]
    assert [item["item_id"] for item in listed["items"]] == [
        str(linked_vehicle.id)
    ]
    assert [item["title"] for item in listed["items"]] == ["BMW"]
    assert listed["vehicles_count"] == 2
    assert listed["items_count"] == 2
    assert Decimal(str(listed["total_amount"])) == Decimal("3740000.00")
    assert Decimal(str(listed["total_vehicles_price"])) == Decimal("3740000.00")
    assert Decimal(str(listed["total_items_price"])) == Decimal("3740000.00")

    detail = await client.get(
        f"/api/v1/applications/{application.id}",
        headers=_auth(distributor_token),
    )
    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert [item["id"] for item in body["items"]] == [str(linked_line.id)]
    assert [item["item_id"] for item in body["items"]] == [str(linked_vehicle.id)]
    assert [item["title"] for item in body["items"]] == ["BMW"]
    assert [vehicle["id"] for vehicle in body["vehicles"]] == [str(linked_line.id)]
    assert [vehicle["vehicle_id"] for vehicle in body["vehicles"]] == [
        str(linked_vehicle.id)
    ]
    assert body["vehicles_count"] == 2
    assert body["items_count"] == 2
    assert Decimal(str(body["total_amount"])) == Decimal("3740000.00")
    assert Decimal(str(body["total_vehicles_price"])) == Decimal("3740000.00")
    assert Decimal(str(body["total_items_price"])) == Decimal("3740000.00")
    assert [row["vehicle_id"] for row in body["vehicle_calculations"]] == [
        str(linked_vehicle.id)
    ]
    for field_name in ("down_payment", "monthly_payment", "total_cost"):
        assert body[field_name] is None
    calculation = body["calculation"]
    assert Decimal(str(calculation["base_total"])) == Decimal("3740000.00")
    for field_name in (
        "monthly_payment",
        "rate",
        "total_cost",
        "total_interest",
        "vehicle_discount_support",
        "effective_total",
    ):
        assert calculation[field_name] is None
    assert [
        row["vehicle_id"] for row in calculation["calculations_per_vehicle"]
    ] == [str(linked_vehicle.id)]
    assert [
        row["vehicle_id"] for row in calculation["support_per_vehicle"]
    ] == [str(linked_vehicle.id)]
    assert calculation["selected_support"] == {
        str(linked_vehicle.id): ["linked-program"]
    }
    assert calculation["support_per_program"] == []
    assert calculation["support_program_details"] == []
    assert str(foreign_vehicle.id) not in detail.text
    assert "FAW" not in detail.text


async def test_general_applications_api_keeps_full_mixed_application_for_employee(
    client: AsyncClient,
    employee_token: str,
    mixed_dealer_application: tuple[
        LeasingApplication,
        Vehicle,
        Vehicle,
        ApplicationVehicle,
        ApplicationVehicle,
    ],
) -> None:
    application, linked_vehicle, foreign_vehicle, linked_line, foreign_line = (
        mixed_dealer_application
    )

    listing = await client.get(
        "/api/v1/applications",
        headers=_auth(employee_token),
    )
    assert listing.status_code == 200, listing.text
    listed = next(
        item
        for item in listing.json()["applications"]
        if item["id"] == str(application.id)
    )
    assert {item["id"] for item in listed["items"]} == {
        str(linked_line.id),
        str(foreign_line.id),
    }
    assert {item["item_id"] for item in listed["items"]} == {
        str(linked_vehicle.id),
        str(foreign_vehicle.id),
    }
    assert {item["title"] for item in listed["items"]} == {"BMW", "FAW"}
    assert listed["vehicles_count"] == 3
    assert listed["items_count"] == 3
    assert Decimal(str(listed["total_amount"])) == Decimal("5480000.00")
    assert Decimal(str(listed["total_vehicles_price"])) == Decimal("5480000.00")
    assert Decimal(str(listed["total_items_price"])) == Decimal("5480000.00")
    assert Decimal(str(listed["monthly_payment"])) == Decimal("150000.00")
    assert Decimal(str(listed["total_cost"])) == Decimal("6000000.00")

    detail = await client.get(
        f"/api/v1/applications/{application.id}",
        headers=_auth(employee_token),
    )
    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert {item["id"] for item in body["items"]} == {
        str(linked_line.id),
        str(foreign_line.id),
    }
    assert {vehicle["vehicle_id"] for vehicle in body["vehicles"]} == {
        str(linked_vehicle.id),
        str(foreign_vehicle.id),
    }
    assert {
        row["vehicle_id"] for row in body["vehicle_calculations"]
    } == {str(linked_vehicle.id), str(foreign_vehicle.id)}
    assert {
        row["vehicle_id"]
        for row in body["calculation"]["calculations_per_vehicle"]
    } == {str(linked_vehicle.id), str(foreign_vehicle.id)}
    assert Decimal(str(body["monthly_payment"])) == Decimal("150000.00")
    assert Decimal(str(body["total_cost"])) == Decimal("6000000.00")
    calculation = body["calculation"]
    assert Decimal(str(calculation["base_total"])) == Decimal("5480000.00")
    assert Decimal(str(calculation["effective_total"])) == Decimal("5480000.00")
    assert Decimal(str(calculation["monthly_payment"])) == Decimal("150000.00")
    assert Decimal(str(calculation["total_cost"])) == Decimal("6000000.00")
    assert calculation["selected_support"] == {
        str(linked_vehicle.id): ["linked-program"],
        str(foreign_vehicle.id): ["foreign-program"],
    }
    assert calculation["support_per_program"] == [
        {
            "support_program_id": "foreign-program",
            "totals": {"amount": 100000},
        }
    ]
    assert calculation["support_program_details"] == [{"id": "foreign-program"}]


@pytest.mark.usefixtures("distributor_application_scope")
async def test_applications_listing_uses_linked_dealer_warehouse(
    client: AsyncClient,
    db_session: AsyncSession,
    distributor_token: str,
    distributor_company: Company,
    linked_dealer_company: Company,
    foreign_dealer_company: Company,
    mark_bmw: Mark,
) -> None:
    linked_vehicle = Vehicle(mark_id=mark_bmw.id, status="available")
    foreign_vehicle = Vehicle(mark_id=mark_bmw.id, status="available")
    linked_warehouse = Warehouse(
        address="Linked dealer warehouse", brand="BMW", company_id=linked_dealer_company.id
    )
    foreign_warehouse = Warehouse(
        address="Foreign dealer warehouse", brand="BMW", company_id=foreign_dealer_company.id
    )
    db_session.add_all([linked_vehicle, foreign_vehicle, linked_warehouse, foreign_warehouse])
    await db_session.flush()
    db_session.add_all([
        VehicleWarehouse(vehicle_id=linked_vehicle.id, warehouse_id=linked_warehouse.id),
        VehicleWarehouse(vehicle_id=foreign_vehicle.id, warehouse_id=foreign_warehouse.id),
    ])
    linked_app = LeasingApplication(company_id=distributor_company.id, status="active")
    foreign_app = LeasingApplication(company_id=distributor_company.id, status="active")
    db_session.add_all([linked_app, foreign_app])
    await db_session.flush()
    db_session.add_all([
        ApplicationVehicle(application_id=linked_app.id, vehicle_id=linked_vehicle.id, quantity=1),
        ApplicationVehicle(application_id=foreign_app.id, vehicle_id=foreign_vehicle.id, quantity=1),
    ])
    await db_session.flush()

    response = await client.get("/api/v1/distributor/applications", headers=_auth(distributor_token))
    assert response.status_code == 200, response.text
    ids = {row["id"] for row in response.json()["applications"]}
    assert str(linked_app.id) in ids
    assert str(foreign_app.id) not in ids


# ---------------------------------------------------------------------------
# G3 — analytics
# /distributor/profile was consolidated into /users/me in Phase 13 R13a.
# Tests for the unified surface live in tests/integration/test_users_me_router.py.
# ---------------------------------------------------------------------------


async def test_legacy_analytics_endpoint_is_not_registered(
    client: AsyncClient,
    db_session: AsyncSession,
    distributor_token: str,
    distributor_company: Company,
    linked_dealer_company: Company,
    mark_bmw: Mark,
) -> None:
    db_session.add(
        Vehicle(
            mark_id=mark_bmw.id,
            status="available",
            dealer_id=linked_dealer_company.id,
        )
    )
    await db_session.flush()
    response = await client.get(
        "/api/v1/distributor/analytics",
        headers=_auth(distributor_token),
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# G3 — dealers / support programs
# ---------------------------------------------------------------------------


async def test_dealers_endpoint(
    client: AsyncClient,
    db_session: AsyncSession,
    distributor_token: str,
    distributor_company: Company,
    linked_dealer_company: Company,
    mark_bmw: Mark,
) -> None:
    db_session.add(
        Vehicle(
            mark_id=mark_bmw.id,
            status="available",
            dealer_id=linked_dealer_company.id,
        )
    )
    await db_session.flush()
    response = await client.get(
        "/api/v1/distributor/dealers",
        headers=_auth(distributor_token),
    )
    assert response.status_code == 200
    dealers = response.json()["dealers"]
    assert any(d["id"] == str(linked_dealer_company.id) for d in dealers)


async def test_support_programs_endpoint(
    client: AsyncClient,
    db_session: AsyncSession,
    distributor_token: str,
    distributor_row: Distributor,
    mark_bmw: Mark,
    model_x5: CarModel,
) -> None:
    lc_company = Company(name="Support LC", company_type="leasing_company")
    db_session.add(lc_company)
    await db_session.flush()
    lc = LeasingCompany(company_id=lc_company.id, is_active=True)
    db_session.add(lc)
    await db_session.flush()
    assert distributor_row.company_id is not None

    program = SupportProgram(
        name="Distributor Support",
        mark_id=mark_bmw.id,
        model_id=model_x5.id,
        model_ids=[model_x5.id],
        distributor_id=distributor_row.company_id,
        support_type="down_payment_compensation",
        support_params={"value_type": "amount", "value": 1000},
        is_active=True,
    )
    db_session.add(program)
    await db_session.flush()
    db_session.add_all(
        [
            SupportProgramDistributor(
                support_program_id=program.id,
                distributor_id=distributor_row.company_id,
            ),
            SupportProgramLeasingCompany(
                support_program_id=program.id,
                leasing_company_id=lc.id,
            ),
            CompensationTemplateModel(
                support_program_id=program.id,
                payer="distributor",
                recipient="leasing_company",
                calculation_base="down_payment",
                value_type="percent",
                value=5,
                payment_schedule_type="reporting_period",
                payment_schedule_period="month",
            ),
        ]
    )
    await db_session.flush()

    response = await client.get(
        "/api/v1/distributor/support-programs",
        headers=_auth(distributor_token),
    )
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"items", "pagination"}
    support = next(item for item in body["items"] if item["id"] == str(program.id))
    assert support["mark_name"] == "BMW"
    assert support["model_name"] == "X5"
    assert support["leasing_companies"][0]["name"] == "Support LC"
    assert support["compensation_templates"][0]["payer"] == "distributor"


# ---------------------------------------------------------------------------
# G3 — applications-grouped / application vehicles
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("distributor_application_scope")
async def test_applications_grouped_endpoint(
    client: AsyncClient,
    db_session: AsyncSession,
    distributor_token: str,
    distributor_company: Company,
    linked_dealer_company: Company,
    mark_bmw: Mark,
) -> None:
    vehicle = Vehicle(
        mark_id=mark_bmw.id,
        status="available",
        dealer_id=linked_dealer_company.id,
    )
    db_session.add(vehicle)
    await db_session.flush()
    await _bind_application_stock(db_session, vehicle, linked_dealer_company)
    app_row = LeasingApplication(company_id=distributor_company.id, status="active")
    db_session.add(app_row)
    await db_session.flush()
    db_session.add(
        ApplicationVehicle(application_id=app_row.id, vehicle_id=vehicle.id, quantity=1)
    )
    await db_session.flush()

    response = await client.get(
        "/api/v1/distributor/applications-grouped",
        headers=_auth(distributor_token),
    )
    assert response.status_code == 200
    grouped = response.json()["applications"]
    assert "active" in grouped


@pytest.mark.usefixtures("distributor_application_scope")
async def test_add_and_list_application_vehicles(
    client: AsyncClient,
    db_session: AsyncSession,
    distributor_token: str,
    distributor_company: Company,
    linked_dealer_company: Company,
    mark_bmw: Mark,
) -> None:
    vehicle = Vehicle(
        mark_id=mark_bmw.id,
        status="available",
        dealer_id=linked_dealer_company.id,
        base_price=Decimal("1000000"),
    )
    db_session.add(vehicle)
    await db_session.flush()
    await _bind_application_stock(db_session, vehicle, linked_dealer_company)
    app_row = LeasingApplication(company_id=distributor_company.id, status="active")
    db_session.add(app_row)
    await db_session.flush()

    add_resp = await client.post(
        f"/api/v1/distributor/applications/{app_row.id}/vehicles",
        json={"vehicle_id": vehicle.id, "quantity": 1},
        headers=_auth(distributor_token),
    )
    assert add_resp.status_code == 200, add_resp.text

    list_resp = await client.get(
        f"/api/v1/distributor/applications/{app_row.id}/vehicles",
        headers=_auth(distributor_token),
    )
    assert list_resp.status_code == 200
    assert len(list_resp.json()["vehicles"]) == 1


async def test_pdf_endpoint_returns_501(
    client: AsyncClient,
    distributor_token: str,
) -> None:
    response = await client.get(
        "/api/v1/distributor/applications/a0b1c2d3-e4f5-6789-0123-456789abcdef/pdf",
        headers=_auth(distributor_token),
    )
    assert response.status_code == 501


# ---------------------------------------------------------------------------
# G3 — available vehicles for app
# ---------------------------------------------------------------------------


async def test_available_vehicles_for_app(
    client: AsyncClient,
    db_session: AsyncSession,
    distributor_token: str,
    distributor_company: Company,
    linked_dealer_company: Company,
    mark_bmw: Mark,
) -> None:
    db_session.add_all(
        [
            Vehicle(
                mark_id=mark_bmw.id,
                status="available",
                dealer_id=linked_dealer_company.id,
            ),
            Vehicle(
                mark_id=mark_bmw.id,
                status="sold",
                dealer_id=linked_dealer_company.id,
            ),
        ]
    )
    await db_session.flush()
    response = await client.get(
        "/api/v1/distributor/available-vehicles-for-app",
        headers=_auth(distributor_token),
    )
    assert response.status_code == 200
    statuses = {v["status"] for v in response.json()["vehicles"]}
    assert statuses == {"available"}


# ---------------------------------------------------------------------------
# G3 — model orders
# ---------------------------------------------------------------------------


async def test_model_orders_endpoints(
    client: AsyncClient,
    db_session: AsyncSession,
    distributor_token: str,
    distributor_company: Company,
    linked_dealer_company: Company,
    mark_bmw: Mark,
) -> None:
    vehicle = Vehicle(
        mark_id=mark_bmw.id,
        status="available",
        dealer_id=linked_dealer_company.id,
    )
    db_session.add(vehicle)
    await db_session.flush()
    app_row = LeasingApplication(company_id=distributor_company.id, status="active")
    db_session.add(app_row)
    await db_session.flush()
    av = ApplicationVehicle(
        application_id=app_row.id,
        vehicle_id=vehicle.id,
        quantity=1,
        is_model_order=True,
    )
    db_session.add(av)
    await db_session.flush()

    stats_resp = await client.get(
        "/api/v1/distributor/model-orders/stats",
        headers=_auth(distributor_token),
    )
    assert stats_resp.status_code == 200
    assert "stats" in stats_resp.json()

    assign_resp = await client.patch(
        f"/api/v1/application-vehicles/{av.id}",
        json={"vin": "MODELVIN0001"},
        headers=_auth(distributor_token),
    )
    assert assign_resp.status_code == 200, assign_resp.text
    assert assign_resp.json()["order"]["vin"] == "MODELVIN0001"


# ---------------------------------------------------------------------------
# G3 — replace / delete application vehicle
# ---------------------------------------------------------------------------


async def test_replace_application_vehicle_endpoint(
    client: AsyncClient,
    db_session: AsyncSession,
    distributor_token: str,
    distributor_company: Company,
    linked_dealer_company: Company,
    mark_bmw: Mark,
) -> None:
    old = Vehicle(
        mark_id=mark_bmw.id, status="reserved", dealer_id=linked_dealer_company.id
    )
    new = Vehicle(
        mark_id=mark_bmw.id, status="available", dealer_id=linked_dealer_company.id
    )
    db_session.add_all([old, new])
    await db_session.flush()
    app_row = LeasingApplication(company_id=distributor_company.id, status="active")
    db_session.add(app_row)
    await db_session.flush()
    av = ApplicationVehicle(application_id=app_row.id, vehicle_id=old.id, quantity=1)
    db_session.add(av)
    await db_session.flush()

    resp = await client.put(
        f"/api/v1/distributor/application-vehicles/{av.id}/replace",
        json={"new_vehicle_id": new.id},
        headers=_auth(distributor_token),
    )
    assert resp.status_code == 200, resp.text


async def test_delete_application_vehicle_endpoint(
    client: AsyncClient,
    db_session: AsyncSession,
    distributor_token: str,
    distributor_company: Company,
    linked_dealer_company: Company,
    mark_bmw: Mark,
) -> None:
    vehicle = Vehicle(
        mark_id=mark_bmw.id,
        status="reserved",
        dealer_id=linked_dealer_company.id,
    )
    db_session.add(vehicle)
    await db_session.flush()
    app_row = LeasingApplication(company_id=distributor_company.id, status="active")
    db_session.add(app_row)
    await db_session.flush()
    av = ApplicationVehicle(
        application_id=app_row.id, vehicle_id=vehicle.id, quantity=1
    )
    db_session.add(av)
    await db_session.flush()

    resp = await client.delete(
        f"/api/v1/distributor/application-vehicles/{av.id}",
        headers=_auth(distributor_token),
    )
    assert resp.status_code == 200, resp.text


# ---------------------------------------------------------------------------
# Phase 10 R6 — collection-level PATCH/DELETE/GET batch-read
# ---------------------------------------------------------------------------


async def test_delete_vehicle_endpoint(
    client: AsyncClient,
    db_session: AsyncSession,
    distributor_token: str,
    distributor_company: Company,
    linked_dealer_company: Company,
    mark_bmw: Mark,
) -> None:
    vehicle = Vehicle(
        mark_id=mark_bmw.id,
        status="available",
        dealer_id=linked_dealer_company.id,
    )
    db_session.add(vehicle)
    await db_session.flush()
    resp = await client.delete(
        f"/api/v1/distributor/vehicles/{vehicle.id}",
        headers=_auth(distributor_token),
    )
    assert resp.status_code == 200, resp.text


async def test_bulk_delete_vehicles_in_scope(
    client: AsyncClient,
    db_session: AsyncSession,
    distributor_token: str,
    distributor_company: Company,
    linked_dealer_company: Company,
    mark_bmw: Mark,
) -> None:
    v1 = Vehicle(
        mark_id=mark_bmw.id,
        status="available",
        dealer_id=linked_dealer_company.id,
    )
    v2 = Vehicle(
        mark_id=mark_bmw.id,
        status="available",
        dealer_id=linked_dealer_company.id,
    )
    db_session.add_all([v1, v2])
    await db_session.flush()
    ids = [v1.id, v2.id]
    resp = await client.request(
        "DELETE",
        "/api/v1/distributor/vehicles",
        json={"ids": ids},
        headers=_auth(distributor_token),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["deleted_count"] == 2
    assert sorted(body["ids"]) == sorted(str(i) for i in ids)


async def test_bulk_delete_vehicles_blocks_out_of_scope(
    client: AsyncClient,
    db_session: AsyncSession,
    distributor_token: str,
    distributor_company: Company,
    linked_dealer_company: Company,
    foreign_dealer_company: Company,
    mark_bmw: Mark,
) -> None:
    own = Vehicle(
        mark_id=mark_bmw.id,
        status="available",
        dealer_id=linked_dealer_company.id,
    )
    foreign = Vehicle(
        mark_id=mark_bmw.id,
        status="available",
        dealer_id=foreign_dealer_company.id,
    )
    db_session.add_all([own, foreign])
    await db_session.flush()

    resp = await client.request(
        "DELETE",
        "/api/v1/distributor/vehicles",
        json={"ids": [own.id, foreign.id]},
        headers=_auth(distributor_token),
    )
    assert resp.status_code == 403


async def test_batch_read_vehicles_by_ids(
    client: AsyncClient,
    db_session: AsyncSession,
    distributor_token: str,
    distributor_company: Company,
    linked_dealer_company: Company,
    mark_bmw: Mark,
) -> None:
    v1 = Vehicle(
        mark_id=mark_bmw.id,
        status="available",
        dealer_id=linked_dealer_company.id,
    )
    v2 = Vehicle(
        mark_id=mark_bmw.id,
        status="available",
        dealer_id=linked_dealer_company.id,
    )
    db_session.add_all([v1, v2])
    await db_session.flush()
    resp = await client.get(
        f"/api/v1/distributor/vehicles?ids={v1.id}&ids={v2.id}",
        headers=_auth(distributor_token),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert {item["id"] for item in body["vehicles"]} == {str(v1.id), str(v2.id)}
    assert body["pagination"]["total"] == 2


# ---------------------------------------------------------------------------
# G3 — import / import-preview / import-template / export
# ---------------------------------------------------------------------------


async def test_import_preview_endpoint(
    client: AsyncClient,
    distributor_token: str,
) -> None:
    headers = ["VIN", "Марка", "Модель", "Базовая цена"]
    rows = [
        ["PREVIEW001", "BMW", "X5", 1000000],
        ["", "Ford", "Focus", 500000],
    ]
    file_bytes = await write_workbook(headers, rows)
    response = await client.post(
        "/api/v1/distributor/vehicles/import-preview",
        files={
            "file": (
                "preview.xlsx",
                file_bytes,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
        headers=_auth(distributor_token),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total_rows"] == 2
    assert body["vehicles_count"] == 1
    assert body["rows_without_vin"] == 1


async def test_import_template_endpoint(
    client: AsyncClient,
    distributor_token: str,
) -> None:
    response = await client.get(
        "/api/v1/distributor/vehicles/import-template",
        headers=_auth(distributor_token),
    )
    assert response.status_code == 200
    # Streaming binary; just sanity-check bytes and headers.
    assert len(response.content) > 0
    assert "attachment" in response.headers["content-disposition"]


async def test_import_alias_endpoint(
    client: AsyncClient,
    distributor_token: str,
    mark_bmw: Mark,
    model_x5: CarModel,
) -> None:
    # Fixtures mark_bmw/model_x5 ensure the catalog is seeded before the
    # xlsx importer tries to resolve "BMW"/"X5" into FK ids.
    assert mark_bmw.id == "bmw_dist"
    assert model_x5.id == "x5_dist"
    headers = ["VIN", "Марка", "Модель", "Год", "Базовая цена"]
    rows = [["ALIASVIN001", "BMW", "X5", 2024, 1000000]]
    file_bytes = await write_workbook(headers, rows)
    response = await client.post(
        "/api/v1/distributor/vehicles/import",
        files={
            "file": (
                "import.xlsx",
                file_bytes,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
        headers=_auth(distributor_token),
    )
    assert response.status_code == 200, response.text
    assert response.json()["imported"] == 1


async def test_vehicles_list_xlsx_format(
    client: AsyncClient,
    db_session: AsyncSession,
    distributor_token: str,
    distributor_company: Company,
    linked_dealer_company: Company,
    mark_bmw: Mark,
) -> None:
    db_session.add(
        Vehicle(
            mark_id=mark_bmw.id,
            status="available",
            dealer_id=linked_dealer_company.id,
        )
    )
    await db_session.flush()
    response = await client.get(
        "/api/v1/distributor/vehicles?format=xlsx",
        headers=_auth(distributor_token),
    )
    assert response.status_code == 200
    assert len(response.content) > 0
    assert "spreadsheetml.sheet" in response.headers["content-type"]
    assert "attachment" in response.headers["content-disposition"]


async def test_vehicles_list_csv_format(
    client: AsyncClient,
    db_session: AsyncSession,
    distributor_token: str,
    distributor_company: Company,
    linked_dealer_company: Company,
    mark_bmw: Mark,
) -> None:
    db_session.add(
        Vehicle(
            mark_id=mark_bmw.id,
            status="available",
            dealer_id=linked_dealer_company.id,
        )
    )
    await db_session.flush()
    response = await client.get(
        "/api/v1/distributor/vehicles?format=csv",
        headers=_auth(distributor_token),
    )
    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]


async def test_vehicles_list_invalid_format_is_422(
    client: AsyncClient,
    distributor_token: str,
) -> None:
    response = await client.get(
        "/api/v1/distributor/vehicles?format=pdf",
        headers=_auth(distributor_token),
    )
    assert response.status_code == 422


async def test_dealers_list_xlsx_format(
    client: AsyncClient,
    distributor_token: str,
) -> None:
    response = await client.get(
        "/api/v1/distributor/dealers?format=xlsx",
        headers=_auth(distributor_token),
    )
    assert response.status_code == 200
    assert "spreadsheetml.sheet" in response.headers["content-type"]
    assert "attachment" in response.headers["content-disposition"]


async def test_legacy_analytics_xlsx_format_is_not_registered(
    client: AsyncClient,
    distributor_token: str,
) -> None:
    response = await client.get(
        "/api/v1/distributor/analytics?format=xlsx",
        headers=_auth(distributor_token),
    )
    assert response.status_code == 404


async def test_analytics_csv_format_is_422(
    client: AsyncClient,
    distributor_token: str,
) -> None:
    response = await client.get(
        "/api/v1/distributor/analytics?format=csv",
        headers=_auth(distributor_token),
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Phase 14 G1 — brands + vehicle history
# ---------------------------------------------------------------------------


async def test_brands_requires_auth(client: AsyncClient) -> None:
    response = await client.get("/api/v1/distributor/vehicles/brands")
    assert response.status_code == 401


async def test_brands_forbidden_for_client(
    client: AsyncClient, client_token: str
) -> None:
    response = await client.get(
        "/api/v1/distributor/vehicles/brands", headers=_auth(client_token)
    )
    assert response.status_code == 403


async def test_brands_returns_distinct_in_scope(
    client: AsyncClient,
    db_session: AsyncSession,
    distributor_token: str,
    distributor_company: Company,
    linked_dealer_company: Company,
    foreign_dealer_company: Company,
    mark_bmw: Mark,
) -> None:
    audi = Mark(id="audi_dist", name="Audi")
    db_session.add(audi)
    await db_session.flush()

    own_bmw = Vehicle(
        mark_id=mark_bmw.id,
        status="available",
        dealer_id=linked_dealer_company.id,
    )
    own_audi = Vehicle(
        mark_id=audi.id,
        status="available",
        dealer_id=linked_dealer_company.id,
    )
    # A duplicate BMW in scope must collapse to a single "BMW" entry.
    own_bmw_dup = Vehicle(
        mark_id=mark_bmw.id,
        status="reserved",
        dealer_id=linked_dealer_company.id,
    )
    # Foreign mark out of scope — must be filtered out.
    foreign_vw_mark = Mark(id="vw_dist", name="Volkswagen")
    db_session.add(foreign_vw_mark)
    await db_session.flush()
    foreign_vw = Vehicle(
        mark_id=foreign_vw_mark.id,
        status="available",
        dealer_id=foreign_dealer_company.id,
    )
    db_session.add_all([own_bmw, own_audi, own_bmw_dup, foreign_vw])
    await db_session.flush()

    response = await client.get(
        "/api/v1/distributor/vehicles/brands",
        headers=_auth(distributor_token),
    )
    assert response.status_code == 200, response.text
    brands = response.json()["brands"]
    assert sorted(brands) == ["Audi", "BMW"]


async def test_vehicle_history_happy_path(
    client: AsyncClient,
    db_session: AsyncSession,
    distributor_token: str,
    distributor_company: Company,
    linked_dealer_company: Company,
    mark_bmw: Mark,
    model_x5: CarModel,
) -> None:
    own = Vehicle(
        mark_id=mark_bmw.id,
        model_id=model_x5.id,
        status="available",
        dealer_id=linked_dealer_company.id,
    )
    db_session.add(own)
    await db_session.flush()

    response = await client.get(
        f"/api/v1/distributor/vehicles/{own.id}/history",
        headers=_auth(distributor_token),
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert "history" in payload
    assert isinstance(payload["history"], list)
    # At minimum a "created" entry is present.
    assert any(e["action"] == "created" for e in payload["history"])


async def test_vehicle_history_unknown_is_404(
    client: AsyncClient,
    distributor_token: str,
) -> None:
    response = await client.get(
        "/api/v1/distributor/vehicles/00000000-0000-0000-0000-000000000000/history",
        headers=_auth(distributor_token),
    )
    assert response.status_code == 404


async def test_vehicle_history_foreign_is_403(
    client: AsyncClient,
    db_session: AsyncSession,
    distributor_token: str,
    foreign_dealer_company: Company,
    mark_bmw: Mark,
) -> None:
    foreign = Vehicle(
        mark_id=mark_bmw.id,
        status="available",
        dealer_id=foreign_dealer_company.id,
    )
    db_session.add(foreign)
    await db_session.flush()

    response = await client.get(
        f"/api/v1/distributor/vehicles/{foreign.id}/history",
        headers=_auth(distributor_token),
    )
    assert response.status_code == 403
