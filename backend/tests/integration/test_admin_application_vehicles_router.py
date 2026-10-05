"""Integration tests for /api/v1/admin/application-vehicles + unified
/api/v1/application-vehicles VIN routes (Phase 13 R13c)."""
from __future__ import annotations

from collections.abc import Generator
from decimal import Decimal
from typing import Any, cast
from uuid import uuid4

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
    DistributorBrand,
    DistributorDealerLink,
)
from infrastructure.models.support import DealerGroup, DealerGroupMember
from infrastructure.models.users import User
from infrastructure.models.vehicles import Warehouse
from infrastructure.services.object_storage import set_object_storage
from tests.fakes.object_storage import FakeObjectStorage
from tests.legacy_compat import Mark, Vehicle, VehicleWarehouse

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def _fake_storage() -> Generator[FakeObjectStorage, None, None]:
    fake = FakeObjectStorage()
    set_object_storage(fake)
    yield fake
    set_object_storage(None)


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def company(db_session: AsyncSession) -> Company:
    company = Company(
        name="ООО Тест",
        inn="1234567890",
        company_type="dealer",
    )
    db_session.add(company)
    await db_session.flush()
    return company


@pytest_asyncio.fixture
async def application(
    db_session: AsyncSession, company: Company
) -> LeasingApplication:
    app = LeasingApplication(company_id=company.id, status="active")
    db_session.add(app)
    await db_session.flush()
    return app


@pytest_asyncio.fixture
async def application_vehicle(
    db_session: AsyncSession, application: LeasingApplication
) -> ApplicationVehicle:
    av = ApplicationVehicle(
        application_id=application.id,
        dealer_company_id=application.company_id,
        modification_id="modif-iv-1",
        quantity=1,
        unit_price=Decimal("3000000.00"),
        total_price=Decimal("3000000.00"),
    )
    db_session.add(av)
    await db_session.flush()
    return av


@pytest_asyncio.fixture
async def dealer_token(db_session: AsyncSession, company: Company) -> str:
    dealer = User(phone=f"+7{uuid4().int % 10**16:016d}", role="dealer",
                  company_id=company.id, is_active=True)
    db_session.add(dealer)
    await db_session.flush()
    token, _ = generate_tokens(dealer.id, "dealer", company.id)
    return token


@pytest_asyncio.fixture
async def vehicle_available(db_session: AsyncSession) -> Vehicle:
    v = Vehicle(
        vin="AVTEST_AVAIL_0001",
        complectation_id="modif-iv-1",
        status="available",
        is_available=True,
    )
    db_session.add(v)
    await db_session.flush()
    return v


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


async def test_assign_vin_anon_unauthorised(
    client: AsyncClient, application_vehicle: ApplicationVehicle
) -> None:
    response = await client.patch(
        f"/api/v1/application-vehicles/{application_vehicle.id}",
        json={"vin": "AVTEST_AVAIL_0001"},
    )
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# Assign VIN — by vehicle_id
# ---------------------------------------------------------------------------


async def test_assign_vin_by_vehicle_id(
    client: AsyncClient,
    employee_token: str,
    application_vehicle: ApplicationVehicle,
    vehicle_available: Vehicle,
) -> None:
    response = await client.patch(
        f"/api/v1/application-vehicles/{application_vehicle.id}",
        json={"vehicle_id": vehicle_available.id},
        headers=_auth(employee_token),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["vin"] == vehicle_available.vin


async def test_assign_vin_unknown_vehicle_returns_404(
    client: AsyncClient,
    employee_token: str,
    application_vehicle: ApplicationVehicle,
) -> None:
    response = await client.patch(
        f"/api/v1/application-vehicles/{application_vehicle.id}",
        json={"vehicle_id": str(uuid4())},
        headers=_auth(employee_token),
    )
    assert response.status_code == 404


async def test_assign_vin_unknown_app_vehicle_returns_404(
    client: AsyncClient, employee_token: str
) -> None:
    response = await client.patch(
        f"/api/v1/application-vehicles/{uuid4()}",
        json={"vin": "WHATEVER"},
        headers=_auth(employee_token),
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Dealer actions
# ---------------------------------------------------------------------------


async def test_dealer_action_accepts_comment_and_multiple_documents(
    client: AsyncClient,
    employee_token: str,
    application_vehicle: ApplicationVehicle,
) -> None:
    response = await client.post(
        f"/api/v1/application-vehicles/{application_vehicle.id}/dealer-action",
        data={"action": "reject", "comment": "Невозможно поставить"},
        files=[
            ("files", ("invoice.pdf", b"%PDF dealer invoice", "application/pdf")),
            ("files", ("photo.jpg", b"dealer photo", "image/jpeg")),
        ],
        headers=_auth(employee_token),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["application_vehicle"]["dealer_comment"] == "Невозможно поставить"
    docs = body["application_vehicle"]["dealer_action_documents"]
    assert [doc["file_name"] for doc in docs] == ["invoice.pdf", "photo.jpg"]
    assert {doc["action"] for doc in docs} == {"reject"}


@pytest.mark.parametrize(
    ("action", "payload", "expected_status"),
    [
        ("reject", {"comment": "Нет автомобиля"}, "not_confirmed"),
        ("replace", {"comment": "Предложим замену"}, "replacement"),
        ("contact_client", {"comment": "Связались с клиентом"}, "active"),
    ],
)
async def test_dealer_action_updates_vehicle_status_and_business_fields(
    client: AsyncClient,
    employee_token: str,
    application_vehicle: ApplicationVehicle,
    action: str,
    payload: dict[str, str],
    expected_status: str,
) -> None:
    response = await client.post(
        f"/api/v1/application-vehicles/{application_vehicle.id}/dealer-action",
        json={"action": action, **payload},
        headers=_auth(employee_token),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    vehicle = body["application_vehicle"]
    assert body["status"] == expected_status
    assert vehicle["status"] == expected_status
    assert vehicle["car_status"] == expected_status
    assert vehicle["dealer_comment"] == payload["comment"]
    if action == "reserve":
        assert vehicle["reserve_expires_at"] == "2026-07-01"


async def test_discount_and_markup_are_combined_from_catalog_snapshot(
    client: AsyncClient,
    db_session: AsyncSession,
    dealer_token: str,
    application: LeasingApplication,
    application_vehicle: ApplicationVehicle,
) -> None:
    cast("Any", application).down_payment_percent = Decimal("20.00")
    application.lease_term_months = 36
    application_vehicle.quantity = 2
    application_vehicle.equipments = [{"price": "100000.00"}]
    application_vehicle.services = [{"price": "50000.00"}]
    calculation = LeasingApplicationCalculation(
        leasing_application_id=application.id,
        rate=Decimal("15.00"),
        total_cost=Decimal("7200000.00"),
        vat_refund=Decimal("1200000.00"),
        profit_tax_savings=Decimal("1200000.00"),
        effective_total=Decimal("6000000.00"),
    )
    db_session.add(calculation)
    await db_session.flush()

    discount_response = await client.post(
        f"/api/v1/application-vehicles/{application_vehicle.id}/dealer-action",
        json={
            "action": "discount",
            "comment": "Скидка согласована",
            "discount_type": "rubles_off",
            "discount_value": "150000.00",
            "final_price": "1.00",
        },
        headers=_auth(dealer_token),
    )

    assert discount_response.status_code == 200, discount_response.text
    discount_body = discount_response.json()
    discounted = discount_body["application_vehicle"]
    assert discount_body["status"] == "confirmed"
    assert discounted["status"] == "confirmed"
    assert discounted["car_status"] == "confirmed"
    await db_session.refresh(application_vehicle)
    assert application_vehicle.car_status == "confirmed"
    assert Decimal(str(discounted["catalog_price"])) == Decimal("3000000.00")
    assert Decimal(str(discounted["final_price"])) == Decimal("2850000.00")
    assert Decimal(str(discounted["total_price"])) == Decimal("6000000.00")

    markup_response = await client.post(
        f"/api/v1/application-vehicles/{application_vehicle.id}/dealer-action",
        json={
            "action": "markup",
            "comment": "Добавили надбавку",
            "markup_type": "rubles_up",
            "markup_value": "200000.00",
        },
        headers=_auth(dealer_token),
    )

    assert markup_response.status_code == 200, markup_response.text
    adjusted = markup_response.json()["application_vehicle"]
    assert Decimal(str(adjusted["discount_value"])) == Decimal("150000.00")
    assert adjusted["markup_type"] == "rubles_up"
    assert Decimal(str(adjusted["markup_value"])) == Decimal("200000.00")
    assert Decimal(str(adjusted["final_price"])) == Decimal("3050000.00")
    assert Decimal(str(adjusted["total_price"])) == Decimal("6400000.00")
    await db_session.refresh(application)
    await db_session.refresh(calculation)
    assert application.total_amount == Decimal("6400000.00")
    assert calculation.base_total == Decimal("6400000.00")
    assert calculation.effective_total == Decimal("6400000.00")
    assert calculation.monthly_payment is not None


async def test_price_visibility_flags_are_independent_for_json_actions(
    client: AsyncClient,
    dealer_token: str,
    application_vehicle: ApplicationVehicle,
) -> None:
    discount_response = await client.post(
        f"/api/v1/application-vehicles/{application_vehicle.id}/dealer-action",
        json={
            "action": "discount",
            "discount_type": "rubles_off",
            "discount_value": "100000.00",
            "show_catalog_price": False,
        },
        headers=_auth(dealer_token),
    )

    assert discount_response.status_code == 200, discount_response.text
    discounted = discount_response.json()["application_vehicle"]
    assert discounted["discount_show_catalog_price"] is False
    assert discounted["markup_show_catalog_price"] is True
    assert discounted["show_catalog_price"] is False

    markup_response = await client.post(
        f"/api/v1/application-vehicles/{application_vehicle.id}/dealer-action",
        json={
            "action": "markup",
            "markup_type": "rubles_up",
            "markup_value": "50000.00",
            "show_catalog_price": True,
        },
        headers=_auth(dealer_token),
    )

    assert markup_response.status_code == 200, markup_response.text
    adjusted = markup_response.json()["application_vehicle"]
    assert adjusted["discount_show_catalog_price"] is False
    assert adjusted["markup_show_catalog_price"] is True
    assert adjusted["show_catalog_price"] is False


async def test_omitted_catalog_visibility_keeps_saved_action_flag(
    client: AsyncClient,
    db_session: AsyncSession,
    dealer_token: str,
    application_vehicle: ApplicationVehicle,
) -> None:
    application_vehicle.discount_show_catalog_price = False
    await db_session.flush()

    response = await client.post(
        f"/api/v1/application-vehicles/{application_vehicle.id}/dealer-action",
        json={
            "action": "discount",
            "discount_type": "rubles_off",
            "discount_value": "200000.00",
        },
        headers=_auth(dealer_token),
    )

    assert response.status_code == 200, response.text
    adjusted = response.json()["application_vehicle"]
    assert adjusted["discount_show_catalog_price"] is False
    assert adjusted["markup_show_catalog_price"] is True
    assert adjusted["show_catalog_price"] is False


async def test_non_price_action_ignores_catalog_visibility(
    client: AsyncClient,
    db_session: AsyncSession,
    dealer_token: str,
    application_vehicle: ApplicationVehicle,
) -> None:
    application_vehicle.discount_show_catalog_price = True
    application_vehicle.markup_show_catalog_price = True
    await db_session.flush()

    response = await client.post(
        f"/api/v1/application-vehicles/{application_vehicle.id}/dealer-action",
        json={
            "action": "reject",
            "comment": "Флаг цены не относится к отказу",
            "show_catalog_price": False,
        },
        headers=_auth(dealer_token),
    )

    assert response.status_code == 200, response.text
    adjusted = response.json()["application_vehicle"]
    assert adjusted["discount_show_catalog_price"] is True
    assert adjusted["markup_show_catalog_price"] is True
    assert adjusted["show_catalog_price"] is True


async def test_multipart_price_action_parses_false_catalog_visibility(
    client: AsyncClient,
    dealer_token: str,
    application_vehicle: ApplicationVehicle,
) -> None:
    response = await client.post(
        f"/api/v1/application-vehicles/{application_vehicle.id}/dealer-action",
        data={
            "action": "markup",
            "markup_type": "rubles_up",
            "markup_value": "50000.00",
            "show_catalog_price": "false",
        },
        files=[("_multipart", (None, "1"))],
        headers=_auth(dealer_token),
    )

    assert response.status_code == 200, response.text
    adjusted = response.json()["application_vehicle"]
    assert adjusted["discount_show_catalog_price"] is True
    assert adjusted["markup_show_catalog_price"] is False
    assert adjusted["show_catalog_price"] is False


async def test_employee_cannot_change_discount(
    client: AsyncClient,
    employee_token: str,
    application_vehicle: ApplicationVehicle,
) -> None:
    response = await client.post(
        f"/api/v1/application-vehicles/{application_vehicle.id}/dealer-action",
        json={
            "action": "discount",
            "discount_type": "rubles_off",
            "discount_value": "1000.00",
        },
        headers=_auth(employee_token),
    )
    assert response.status_code == 400


async def test_other_dealer_cannot_change_vehicle_price(
    client: AsyncClient,
    db_session: AsyncSession,
    company: Company,
    application_vehicle: ApplicationVehicle,
) -> None:
    other_company = Company(name="Другой дилер", company_type="dealer", is_active=True)
    db_session.add(other_company)
    await db_session.flush()
    other_dealer = User(phone=f"+7{uuid4().int % 10**16:016d}", role="dealer",
                        company_id=other_company.id, is_active=True)
    db_session.add(other_dealer)
    await db_session.flush()
    assert other_company.id != company.id
    token, _ = generate_tokens(other_dealer.id, "dealer", other_company.id)
    response = await client.post(
        f"/api/v1/application-vehicles/{application_vehicle.id}/dealer-action",
        json={
            "action": "markup",
            "markup_type": "rubles_up",
            "markup_value": "1000.00",
        },
        headers=_auth(token),
    )

    assert response.status_code == 403



async def test_linked_distributor_can_change_vehicle_price(
    client: AsyncClient,
    db_session: AsyncSession,
    company: Company,
    application_vehicle: ApplicationVehicle,
) -> None:
    distributor = Company(
        name="ООО Дистрибьютор",
        inn="123456789012",
        company_type="distributor",
    )
    db_session.add(distributor)
    await db_session.flush()
    db_session.add(
        DistributorDealerLink(
            distributor_company_id=distributor.id,
            dealer_company_id=company.id,
        )
    )
    await db_session.flush()
    distributor_user = User(phone=f"+7{uuid4().int % 10**16:016d}", role="distributor",
                            company_id=distributor.id, is_active=True)
    db_session.add(distributor_user)
    await db_session.flush()
    mark = Mark(id="21864_PRICE", name="Price brand")
    group = DealerGroup(
        distributor_company_id=distributor.id, name="Price dealers",
        created_by=distributor_user.id, is_active=True,
    )
    warehouse = Warehouse(company_id=company.id, address="Dealer stock", brand=mark.name)
    db_session.add_all([mark, group, warehouse])
    await db_session.flush()
    stock_vehicle = Vehicle(mark_id=mark.id, dealer_id=company.id, status="available")
    db_session.add(stock_vehicle)
    await db_session.flush()
    db_session.add_all([
        DistributorBrand(distributor_company_id=distributor.id, brand_id=mark.id, is_active=True),
        DealerGroupMember(dealer_group_id=group.id, dealer_company_id=company.id,
                          created_by=distributor_user.id),
        VehicleWarehouse(vehicle_id=stock_vehicle.id, warehouse_id=warehouse.id),
    ])
    application_vehicle.vehicle_id = stock_vehicle.id
    await db_session.flush()
    token, _ = generate_tokens(distributor_user.id, "distributor", distributor.id)

    response = await client.post(
        f"/api/v1/application-vehicles/{application_vehicle.id}/dealer-action",
        json={
            "action": "markup",
            "markup_type": "rubles_up",
            "markup_value": "1000.00",
        },
        headers=_auth(token),
    )
    assert response.status_code == 200, response.text
    assert response.json()["application_vehicle"]["final_price"] == 3001000.0


async def test_dealer_action_replace_vin_sets_vin_and_marks_replacement(
    client: AsyncClient,
    db_session: AsyncSession,
    employee_token: str,
    application_vehicle: ApplicationVehicle,
) -> None:
    response = await client.post(
        f"/api/v1/application-vehicles/{application_vehicle.id}/dealer-action",
        json={
            "action": "replace_vin",
            "vin": "REPLACEVIN0001",
            "comment": "Заменили VIN",
        },
        headers=_auth(employee_token),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    vehicle = body["application_vehicle"]
    assert body["status"] == "replacement"
    assert vehicle["status"] == "replacement"
    assert vehicle["car_status"] == "replacement"
    assert vehicle["vin"] == "REPLACEVIN0001"
    assert vehicle["dealer_comment"] == "Заменили VIN"
    await db_session.refresh(application_vehicle)
    assert application_vehicle.car_status == "replacement"


# ---------------------------------------------------------------------------
# Assign VIN — manual
# ---------------------------------------------------------------------------


async def test_assign_vin_manual(
    client: AsyncClient,
    employee_token: str,
    application_vehicle: ApplicationVehicle,
) -> None:
    response = await client.patch(
        f"/api/v1/application-vehicles/{application_vehicle.id}",
        json={"vin": "MANUALVIN0001"},
        headers=_auth(employee_token),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["vin"] == "MANUALVIN0001"


async def test_assign_vin_duplicate_across_app_vehicles_returns_409(
    client: AsyncClient,
    db_session: AsyncSession,
    employee_token: str,
    application: LeasingApplication,
    application_vehicle: ApplicationVehicle,
) -> None:
    other_av = ApplicationVehicle(
        application_id=application.id,
        modification_id="modif-iv-1",
        vin="DUPVIN0001",
    )
    db_session.add(other_av)
    await db_session.flush()

    response = await client.patch(
        f"/api/v1/application-vehicles/{application_vehicle.id}",
        json={"vin": "DUPVIN0001"},
        headers=_auth(employee_token),
    )
    assert response.status_code == 409


# ---------------------------------------------------------------------------
# Available VINs
# ---------------------------------------------------------------------------


async def test_available_vins_returns_matching_complectation(
    client: AsyncClient,
    employee_token: str,
    application_vehicle: ApplicationVehicle,
    vehicle_available: Vehicle,
) -> None:
    response = await client.get(
        f"/api/v1/application-vehicles/{application_vehicle.id}/available-vins",
        headers=_auth(employee_token),
    )
    assert response.status_code == 200
    body = response.json()
    vins = [v["vin"] for v in body["vehicles"]]
    assert vehicle_available.vin in vins


async def test_available_vins_unknown_app_vehicle_returns_404(
    client: AsyncClient, employee_token: str
) -> None:
    response = await client.get(
        f"/api/v1/application-vehicles/{uuid4()}/available-vins",
        headers=_auth(employee_token),
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Assign vehicle (dealer)
# ---------------------------------------------------------------------------


async def test_assign_vehicle_requires_existing_vehicle_link(
    client: AsyncClient,
    employee_token: str,
    application_vehicle: ApplicationVehicle,
) -> None:
    response = await client.put(
        f"/api/v1/admin/application-vehicles/{application_vehicle.id}/assign",
        json={"dealer_id": str(uuid4())},
        headers=_auth(employee_token),
    )
    assert response.status_code == 400


async def test_assign_vehicle_after_vin_assignment(
    client: AsyncClient,
    db_session: AsyncSession,
    employee_token: str,
    application_vehicle: ApplicationVehicle,
    vehicle_available: Vehicle,
    company: Company,
) -> None:
    # First link the application_vehicle to a real vehicle.
    await client.patch(
        f"/api/v1/application-vehicles/{application_vehicle.id}",
        json={"vehicle_id": vehicle_available.id},
        headers=_auth(employee_token),
    )
    response = await client.put(
        f"/api/v1/admin/application-vehicles/{application_vehicle.id}/assign",
        json={"dealer_id": company.id},
        headers=_auth(employee_token),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True


async def test_assign_vehicle_unknown_dealer_returns_404(
    client: AsyncClient,
    db_session: AsyncSession,
    employee_token: str,
    application_vehicle: ApplicationVehicle,
    vehicle_available: Vehicle,
) -> None:
    await client.patch(
        f"/api/v1/application-vehicles/{application_vehicle.id}",
        json={"vehicle_id": vehicle_available.id},
        headers=_auth(employee_token),
    )
    response = await client.put(
        f"/api/v1/admin/application-vehicles/{application_vehicle.id}/assign",
        json={"dealer_id": str(uuid4())},
        headers=_auth(employee_token),
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# PATCH /application-vehicles/{id} — role dispatch (Phase 13 R13c)
# ---------------------------------------------------------------------------


async def test_patch_client_not_owner_forbidden(
    client: AsyncClient,
    db_session: AsyncSession,
    application_vehicle: ApplicationVehicle,
    client_token: str,
) -> None:
    """A ``client`` user who does not own the parent application gets 403.

    The role is allowlisted but the ownership check inside the unified
    handler rejects — domain ``ApplicationNotOwnedError`` maps to 403.
    """
    response = await client.patch(
        f"/api/v1/application-vehicles/{application_vehicle.id}",
        json={"vin": "SOMEVIN0001"},
        headers=_auth(client_token),
    )
    assert response.status_code == 403


async def test_legacy_reserve_returns_conflict_without_confirming_line(
    client: AsyncClient, db_session: AsyncSession, employee_token: str,
    application_vehicle: ApplicationVehicle,
) -> None:
    response = await client.post(
        f"/api/v1/application-vehicles/{application_vehicle.id}/dealer-action",
        json={"action": "reserve", "reserve_expires_at": "2099-07-01"},
        headers=_auth(employee_token),
    )
    assert response.status_code == 409
    assert response.json()["detail"] == "Подберите автомобили со склада и сохраните подбор"
    await db_session.refresh(application_vehicle)
    assert application_vehicle.car_status == "active"
    assert application_vehicle.reserve_expires_at is None
    assert application_vehicle.confirmed_quantity is None
