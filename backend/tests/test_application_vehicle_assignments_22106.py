"""Regression coverage for Bitrix 22106 vehicle-level assignments."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import cast
from uuid import UUID

import pytest
import pytest_asyncio
import sqlalchemy as sa
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.auth import generate_tokens
from infrastructure.models.applications import ApplicationVehicle, LeasingApplication
from infrastructure.models.companies import (
    Company,
    DistributorBrand,
    DistributorDealerLink,
)
from infrastructure.models.support import DealerGroup, DealerGroupMember
from infrastructure.models.users import User, UserCompany
from infrastructure.models.vehicles import City, Warehouse
from tests.legacy_compat import Mark, Vehicle, VehicleWarehouse


@dataclass
class VehicleAssignmentGraph:
    distributor: Company
    dealer_one: Company
    dealer_two: Company
    foreign_dealer: Company
    client_company: Company
    distributor_user: User
    dealer_one_user: User
    dealer_one_employee: User
    dealer_two_employee: User
    application: LeasingApplication
    first_car: ApplicationVehicle
    second_car: ApplicationVehicle


async def _add_user(
    session: AsyncSession,
    *,
    company: Company,
    phone: str,
    name: str,
    role: str,
) -> User:
    user = User(
        company_id=company.id,
        phone=phone,
        name=name,
        role=role,
        is_active=True,
    )
    session.add(user)
    await session.flush()
    session.add(
        UserCompany(
            user_id=user.id,
            company_id=company.id,
            sub_role="administrator",
            can_view_applications=True,
            can_create_applications=True,
        )
    )
    await session.flush()
    return user


async def _add_dealer_vehicle(
    session: AsyncSession,
    *,
    dealer: Company,
    city: City,
    vin: str,
) -> Vehicle:
    warehouse = Warehouse(
        company_id=dealer.id,
        dealer_id=dealer.id,
        city_id=city.id,
        brand="FAW",
        address=f"Склад {vin}",
        status="active",
    )
    vehicle = Vehicle(
        dealer_id=dealer.id,
        mark_id="faw-22106",
        vin=vin,
        status="available",
        is_available=True,
        base_price=Decimal("1000000"),
    )
    session.add_all([warehouse, vehicle])
    await session.flush()
    session.add(VehicleWarehouse(vehicle_id=vehicle.id, warehouse_id=warehouse.id))
    await session.flush()
    return vehicle


@pytest_asyncio.fixture
async def vehicle_assignment_graph(
    db_session: AsyncSession,
) -> VehicleAssignmentGraph:
    distributor = Company(
        name="22106 Distributor",
        company_type="distributor",
        is_active=True,
    )
    dealer_one = Company(
        name="22106 Dealer One",
        company_type="dealer",
        is_active=True,
    )
    dealer_two = Company(
        name="22106 Dealer Two",
        company_type="dealer",
        is_active=True,
    )
    foreign_dealer = Company(
        name="22106 Foreign Dealer",
        company_type="dealer",
        is_active=True,
    )
    client_company = Company(
        name="22106 Client",
        company_type="other",
        is_active=True,
    )
    db_session.add_all(
        [distributor, dealer_one, dealer_two, foreign_dealer, client_company]
    )
    await db_session.flush()
    db_session.add_all(
        [
            DistributorDealerLink(
                distributor_company_id=distributor.id,
                dealer_company_id=dealer_one.id,
            ),
        ]
    )
    await db_session.flush()

    distributor_user = await _add_user(
        db_session,
        company=distributor,
        phone="+76662210601",
        name="22106 Distributor User",
        role="distributor",
    )
    dealer_group = DealerGroup(
        distributor_company_id=distributor.id,
        name="22106 Active Dealer Group",
        is_active=True,
        created_by=distributor_user.id,
    )
    db_session.add(dealer_group)
    await db_session.flush()
    db_session.add_all([
        DealerGroupMember(
            dealer_group_id=dealer_group.id,
            dealer_company_id=dealer.id,
            created_by=distributor_user.id,
        )
        for dealer in (dealer_one, dealer_two)
    ])
    db_session.add(Mark(id="faw-22106", name="FAW"))
    await db_session.flush()
    db_session.add(DistributorBrand(
        distributor_company_id=distributor.id, brand_id="faw-22106", is_active=True,
    ))
    await db_session.flush()
    dealer_one_user = await _add_user(
        db_session,
        company=dealer_one,
        phone="+76662210602",
        name="22106 Dealer One User",
        role="dealer",
    )
    dealer_one_employee = await _add_user(
        db_session,
        company=dealer_one,
        phone="+76662210603",
        name="22106 Dealer One Employee",
        role="dealer",
    )
    dealer_two_employee = await _add_user(
        db_session,
        company=dealer_two,
        phone="+76662210604",
        name="22106 Dealer Two Employee",
        role="dealer",
    )

    city = City(name="Москва 22106")
    db_session.add(city)
    await db_session.flush()
    first_vehicle = await _add_dealer_vehicle(
        db_session,
        dealer=dealer_one,
        city=city,
        vin="VIN22106FIRST",
    )
    second_vehicle = await _add_dealer_vehicle(
        db_session,
        dealer=dealer_two,
        city=city,
        vin="VIN22106SECOND",
    )

    application = LeasingApplication(
        company_id=client_company.id,
        name="22106 Vehicle Assignments",
        email="22106@example.test",
        status="active",
    )
    db_session.add(application)
    await db_session.flush()
    first_car = ApplicationVehicle(
        application_id=application.id,
        vehicle_id=first_vehicle.id,
        dealer_company_id=dealer_one.id,
        quantity=1,
        unit_price=Decimal("1000000"),
        total_price=Decimal("1000000"),
    )
    second_car = ApplicationVehicle(
        application_id=application.id,
        vehicle_id=second_vehicle.id,
        dealer_company_id=dealer_two.id,
        quantity=1,
        unit_price=Decimal("1000000"),
        total_price=Decimal("1000000"),
    )
    db_session.add_all([first_car, second_car])
    await db_session.flush()

    return VehicleAssignmentGraph(
        distributor=distributor,
        dealer_one=dealer_one,
        dealer_two=dealer_two,
        foreign_dealer=foreign_dealer,
        client_company=client_company,
        distributor_user=distributor_user,
        dealer_one_user=dealer_one_user,
        dealer_one_employee=dealer_one_employee,
        dealer_two_employee=dealer_two_employee,
        application=application,
        first_car=first_car,
        second_car=second_car,
    )


def _token(user: User) -> str:
    access_token, _ = generate_tokens(
        user.id,
        cast("str", user.role),
        user.company_id,
    )
    return cast("str", access_token)


def _headers(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {_token(user)}"}


def test_application_vehicle_model_owns_assignment_columns() -> None:
    table = cast("sa.Table", ApplicationVehicle.__table__)
    expected_foreign_keys = {
        "dealer_company_id": "companies.id",
        "dealer_assigned_by": "users.id",
        "primary_employee_id": "users.id",
        "additional_employee_id": "users.id",
        "employees_assigned_by": "users.id",
    }
    expected_columns = {
        *expected_foreign_keys,
        "dealer_assigned_at",
        "employees_assigned_at",
    }
    assert expected_columns <= set(table.columns.keys())
    for column_name, target in expected_foreign_keys.items():
        assert table.c[column_name].nullable is True
        foreign_keys = list(table.c[column_name].foreign_keys)
        assert len(foreign_keys) == 1
        assert foreign_keys[0].target_fullname == target
        assert foreign_keys[0].ondelete == "SET NULL"
    index_names = {index.name for index in table.indexes}
    assert {
        "idx_application_vehicles_dealer_company_id",
        "idx_application_vehicles_dealer_assigned_by",
        "idx_application_vehicles_primary_employee_id",
        "idx_application_vehicles_additional_employee_id",
        "idx_application_vehicles_employees_assigned_by",
    } <= index_names


def test_assignment_migration_backfills_every_application_vehicle() -> None:
    versions_dir = Path(__file__).resolve().parents[1] / "alembic" / "versions"
    migration = (
        versions_dir / "090_application_vehicle_assignments.py"
    ).read_text(encoding="utf-8")
    repair = (
        versions_dir / "092_repair_application_vehicle_assignments.py"
    ).read_text(encoding="utf-8")
    assert "application_vehicles" in migration
    assert "leasing_applications" in migration
    assert "vehicle_warehouses" in migration
    assert "warehouses" in migration
    assert "COALESCE(w.company_id, w.dealer_id)" in migration
    assert "WHEN av.vehicle_id IS NULL THEN la.dealer_company_id" in migration
    assert "UPDATE application_vehicles" in migration
    for column_name in (
        "dealer_company_id",
        "dealer_assigned_by",
        "dealer_assigned_at",
        "primary_employee_id",
        "additional_employee_id",
        "employees_assigned_by",
        "employees_assigned_at",
    ):
        assert column_name in migration
    assert 'ondelete="SET NULL"' in migration
    assert "IS NOT DISTINCT FROM la.dealer_company_id" in repair
    assert "COALESCE(w.company_id, w.dealer_id)" in repair
    assert "dealer_assigned_by = NULL" in repair
    assert "primary_employee_id = NULL" in repair


@pytest.mark.asyncio
async def test_retired_put_preserves_both_existing_dealer_assignments(
    client: AsyncClient,
    db_session: AsyncSession,
    vehicle_assignment_graph: VehicleAssignmentGraph,
) -> None:
    graph = vehicle_assignment_graph
    original = [(line.dealer_company_id, line.dealer_assigned_at) for line in (graph.first_car, graph.second_car)]
    for line in (graph.first_car, graph.second_car):
        result = await client.put(
            f"/api/v1/{graph.application.id}/{line.id}/diler",
            json={"dealer_id": graph.dealer_two.id}, headers=_headers(graph.distributor_user),
        )
        assert result.status_code == 409
        assert "dealer-distributions" in result.json()["detail"]["message"]
    for line, before in zip((graph.first_car, graph.second_car), original, strict=True):
        await db_session.refresh(line)
        assert (line.dealer_company_id, line.dealer_assigned_at) == before


@pytest.mark.asyncio
async def test_dealer_cannot_call_distributor_put(
    client: AsyncClient,
    vehicle_assignment_graph: VehicleAssignmentGraph,
) -> None:
    graph = vehicle_assignment_graph
    response = await client.put(
        f"/api/v1/{graph.application.id}/{graph.first_car.id}/diler",
        json={"dealer_id": graph.dealer_one.id},
        headers=_headers(graph.dealer_one_user),
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_put_rejects_dealer_not_linked_to_distributor(
    client: AsyncClient,
    vehicle_assignment_graph: VehicleAssignmentGraph,
) -> None:
    graph = vehicle_assignment_graph
    response = await client.put(
        f"/api/v1/{graph.application.id}/{graph.first_car.id}/diler",
        json={"dealer_id": graph.foreign_dealer.id},
        headers=_headers(graph.distributor_user),
    )

    assert response.status_code == 409
    assert "dealer-distributions" in response.json()["detail"]["message"]


@pytest.mark.asyncio
async def test_employee_assignment_is_scoped_to_the_cars_assigned_dealer(
    client: AsyncClient,
    db_session: AsyncSession,
    vehicle_assignment_graph: VehicleAssignmentGraph,
) -> None:
    graph = vehicle_assignment_graph
    distributor_headers = _headers(graph.distributor_user)
    await client.put(
        f"/api/v1/{graph.application.id}/{graph.first_car.id}/diler",
        json={"dealer_id": graph.dealer_one.id},
        headers=distributor_headers,
    )
    employee_path = (
        f"/api/v1/applications/{graph.application.id}/vehicles/"
        f"{graph.first_car.id}/employees"
    )

    assigned = await client.patch(
        employee_path,
        json={"primary_employee_id": graph.dealer_one_employee.id},
        headers=distributor_headers,
    )
    assert assigned.status_code == 200
    assert assigned.json()["application_vehicle"]["primary_employee"]["id"] == str(
        graph.dealer_one_employee.id
    )

    foreign = await client.patch(
        employee_path,
        json={"additional_employee_id": graph.dealer_two_employee.id},
        headers=distributor_headers,
    )
    assert foreign.status_code == 400

    search = await client.get(
        f"{employee_path}/search",
        params={"query": "22106", "limit": 20},
        headers=distributor_headers,
    )
    assert search.status_code == 200
    employee_ids = {employee["id"] for employee in search.json()["employees"]}
    assert str(graph.dealer_one_employee.id) in employee_ids
    assert str(graph.dealer_two_employee.id) not in employee_ids

    await db_session.refresh(graph.first_car)
    assert graph.first_car.primary_employee_id == graph.dealer_one_employee.id
    assert graph.first_car.additional_employee_id is None


@pytest.mark.asyncio
async def test_retired_reassignment_preserves_both_cars_employees(
    client: AsyncClient,
    db_session: AsyncSession,
    vehicle_assignment_graph: VehicleAssignmentGraph,
) -> None:
    graph = vehicle_assignment_graph
    headers = _headers(graph.distributor_user)
    first_dealer_path = f"/api/v1/{graph.application.id}/{graph.first_car.id}/diler"
    await client.put(
        first_dealer_path,
        json={"dealer_id": graph.dealer_one.id},
        headers=headers,
    )
    await client.put(
        f"/api/v1/{graph.application.id}/{graph.second_car.id}/diler",
        json={"dealer_id": graph.dealer_two.id},
        headers=headers,
    )
    await client.patch(
        f"/api/v1/applications/{graph.application.id}/vehicles/"
        f"{graph.first_car.id}/employees",
        json={"primary_employee_id": graph.dealer_one_employee.id},
        headers=headers,
    )
    await client.patch(
        f"/api/v1/applications/{graph.application.id}/vehicles/"
        f"{graph.second_car.id}/employees",
        json={"primary_employee_id": graph.dealer_two_employee.id},
        headers=headers,
    )

    changed = await client.put(
        first_dealer_path,
        json={"dealer_id": graph.dealer_two.id},
        headers=headers,
    )
    assert changed.status_code == 409

    await db_session.refresh(graph.first_car)
    await db_session.refresh(graph.second_car)
    assert graph.first_car.primary_employee_id == graph.dealer_one_employee.id
    assert graph.first_car.additional_employee_id is None
    assert graph.second_car.primary_employee_id == graph.dealer_two_employee.id


async def _assert_visible_vehicle_ids(
    client: AsyncClient,
    *,
    user: User,
    application_id: UUID,
    expected_ids: set[str],
) -> None:
    headers = _headers(user)
    listing = await client.get(
        "/api/v1/applications?page=1&limit=50",
        headers=headers,
    )
    assert listing.status_code == 200
    listed_application = next(
        application
        for application in listing.json()["applications"]
        if application["id"] == str(application_id)
    )
    listed_vehicle_ids = {
        item["id"]
        for item in listed_application["items"]
        if item["type"] == "vehicle"
    }

    detail = await client.get(
        f"/api/v1/applications/{application_id}",
        headers=headers,
    )
    assert detail.status_code == 200
    detail_vehicle_ids = {vehicle["id"] for vehicle in detail.json()["vehicles"]}
    assert listed_vehicle_ids == expected_ids
    assert detail_vehicle_ids == expected_ids


@pytest.mark.asyncio
async def test_warehouse_owner_and_assigned_dealer_share_vehicle_visibility(
    client: AsyncClient,
    db_session: AsyncSession,
    vehicle_assignment_graph: VehicleAssignmentGraph,
) -> None:
    graph = vehicle_assignment_graph
    graph.application.dealer_company_id = graph.dealer_one.id
    db_session.add(
        DistributorDealerLink(
            distributor_company_id=graph.distributor.id,
            dealer_company_id=graph.foreign_dealer.id,
        )
    )
    assigned_dealer_user = await _add_user(
        db_session,
        company=graph.foreign_dealer,
        phone="+76662210605",
        name="22106 Assigned Dealer User",
        role="dealer",
    )
    await db_session.flush()

    # Historic assignments remain readable after retiring the mutation API.
    graph.first_car.dealer_company_id = graph.foreign_dealer.id
    await db_session.flush()

    first_id = str(graph.first_car.id)
    second_id = str(graph.second_car.id)
    await _assert_visible_vehicle_ids(
        client,
        user=graph.dealer_one_user,
        application_id=graph.application.id,
        expected_ids={first_id},
    )
    await _assert_visible_vehicle_ids(
        client,
        user=assigned_dealer_user,
        application_id=graph.application.id,
        expected_ids={first_id},
    )
    await _assert_visible_vehicle_ids(
        client,
        user=graph.dealer_two_employee,
        application_id=graph.application.id,
        expected_ids={second_id},
    )

    graph.first_car.dealer_company_id = graph.dealer_two.id
    await db_session.flush()

    await _assert_visible_vehicle_ids(
        client,
        user=graph.dealer_one_user,
        application_id=graph.application.id,
        expected_ids={first_id},
    )
    await _assert_visible_vehicle_ids(
        client,
        user=graph.dealer_two_employee,
        application_id=graph.application.id,
        expected_ids={first_id, second_id},
    )
    assigned_listing = await client.get(
        "/api/v1/applications?page=1&limit=50",
        headers=_headers(assigned_dealer_user),
    )
    assert assigned_listing.status_code == 200
    assert str(graph.application.id) not in {
        application["id"]
        for application in assigned_listing.json()["applications"]
    }
    denied_detail = await client.get(
        f"/api/v1/applications/{graph.application.id}",
        headers=_headers(assigned_dealer_user),
    )
    assert denied_detail.status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize("owner_type", ["dealer", "distributor"])
async def test_warehouse_supplier_is_distinct_from_explicit_dealer_assignment(
    client: AsyncClient,
    db_session: AsyncSession,
    vehicle_assignment_graph: VehicleAssignmentGraph,
    owner_type: str,
) -> None:
    graph = vehicle_assignment_graph
    graph.first_car.dealer_company_id = None
    graph.dealer_one.company_type = owner_type
    graph.dealer_one_user.role = owner_type
    await db_session.execute(
        sa.update(Vehicle).where(Vehicle.id == graph.first_car.vehicle_id).values(dealer_id=None)
    )
    await db_session.flush()
    response = await client.get(
        f"/api/v1/applications/{graph.application.id}", headers=_headers(graph.dealer_one_user)
    )
    assert response.status_code == 200
    line = next(item for item in response.json()["vehicles"] if item["id"] == str(graph.first_car.id))
    assert line["assigned_dealer"] is None
    assert line["dealer_company_id"] is None
    if owner_type == "dealer":
        assert line["stock_dealer"]["id"] == str(graph.dealer_one.id)
        assert line["stock_dealer"]["name"] == graph.dealer_one.name
    else:
        assert line["stock_dealer"] is None
