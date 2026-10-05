"""Functional tests for warehouse / city / vehicle-binding handlers."""
from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from application.commands.cities import (
    CreateCityCommand,
    handle_create_city,
)
from application.commands.warehouses import (
    AddVehicleToWarehouseCommand,
    BindVehiclesByMarkCommand,
    CreateWarehouseCommand,
    DeleteWarehouseCommand,
    RemoveVehicleFromWarehouseCommand,
    UpdateWarehouseCommand,
    handle_add_vehicle_to_warehouse,
    handle_bind_vehicles_by_mark,
    handle_delete_warehouse,
    handle_remove_vehicle_from_warehouse,
)
from application.commands.warehouses import (
    handle_create_warehouse as _handle_create_warehouse,
)
from application.commands.warehouses import (
    handle_update_warehouse as _handle_update_warehouse,
)
from application.queries.cities import (
    ListCitiesQuery,
    handle_list_cities,
)
from application.queries.warehouses import (
    GetWarehouseQuery,
    ListWarehousesQuery,
    ListWarehouseVehiclesQuery,
    handle_get_warehouse,
    handle_list_warehouse_vehicles,
    handle_list_warehouses,
)
from domain.errors import (
    CityAlreadyExistsError,
    CityNotFoundError,
    DealerNotFoundError,
    InvalidWarehouseError,
    MarkNotFoundError,
    VehicleAlreadyInWarehouseError,
    VehicleNotFoundError,
    VehicleNotInWarehouseError,
    WarehouseNotFoundError,
)
from infrastructure.models.companies import Company
from infrastructure.models.users import User
from infrastructure.models.vehicles import City, Warehouse
from tests.legacy_compat import Mark, Vehicle


async def handle_create_warehouse(
    command: CreateWarehouseCommand,
    session: AsyncSession,
) -> dict[str, Any]:
    """Unwrap the explicit command result for legacy functional assertions."""

    return (await _handle_create_warehouse(command, session))["warehouse"]


async def handle_update_warehouse(
    command: UpdateWarehouseCommand,
    session: AsyncSession,
) -> dict[str, Any]:
    return (await _handle_update_warehouse(command, session))["warehouse"]


@pytest_asyncio.fixture
async def city_moscow(db_session: AsyncSession) -> City:
    city = City(name="Москва")
    db_session.add(city)
    await db_session.flush()
    return city


@pytest_asyncio.fixture
async def dealer_company(db_session: AsyncSession) -> Company:
    company = Company(
        name="Dealer Company WH",
        company_type="dealer",
        is_active=True,
    )
    db_session.add(company)
    await db_session.flush()
    return company


@pytest_asyncio.fixture
async def dealer_user(db_session: AsyncSession, dealer_company: Company) -> User:
    user = User(
        phone="+76660004444",
        email="dealer-wh@test.local",
        name="Dealer WH",
        role="dealer",
        is_active=True,
        company_id=dealer_company.id,
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest_asyncio.fixture
async def mark_bmw(db_session: AsyncSession) -> Mark:
    mark = Mark(id="bmw_wh", name="BMW")
    db_session.add(mark)
    await db_session.flush()
    return mark


@pytest_asyncio.fixture
async def vehicle_bmw(db_session: AsyncSession, mark_bmw: Mark) -> Vehicle:
    vehicle = Vehicle(
        mark_id=mark_bmw.id,
        vin="BMWVIN0000000001",
        status="available",
        is_available=True,
    )
    db_session.add(vehicle)
    await db_session.flush()
    return vehicle


# ---------------------------------------------------------------------------
# Cities
# ---------------------------------------------------------------------------


async def test_create_city_persists(db_session: AsyncSession) -> None:
    city = await handle_create_city(
        CreateCityCommand(name="Самара"), db_session
    )
    assert city["id"] is not None
    assert city["name"] == "Самара"


async def test_create_city_duplicate_raises(db_session: AsyncSession) -> None:
    await handle_create_city(CreateCityCommand(name="Тула"), db_session)
    with pytest.raises(CityAlreadyExistsError):
        await handle_create_city(
            CreateCityCommand(name="ТУЛА"), db_session
        )


async def test_list_cities_sorted(db_session: AsyncSession) -> None:
    for name in ("Уфа", "Анапа", "Москва"):
        await handle_create_city(CreateCityCommand(name=name), db_session)
    result = await handle_list_cities(ListCitiesQuery(), db_session)
    names = [c["name"] for c in result["cities"]]
    assert names == sorted(names)


# ---------------------------------------------------------------------------
# Warehouses
# ---------------------------------------------------------------------------


async def test_create_warehouse_persists_with_city_and_dealer(
    db_session: AsyncSession,
    city_moscow: City,
    dealer_user: User,
    dealer_company: Company,
) -> None:
    warehouse = await handle_create_warehouse(
        CreateWarehouseCommand(
            address="ул. Тверская, 1",
            brand="BMW",
            city_id=city_moscow.id,
            dealer_id=dealer_company.id,
        ),
        db_session,
    )
    assert warehouse["id"] is not None
    assert warehouse["address"] == "ул. Тверская, 1"
    assert str(warehouse["city_id"]) == str(city_moscow.id)
    assert str(warehouse["dealer_id"]) == str(dealer_company.id)
    assert warehouse["city_name"] == "Москва"


async def test_create_warehouse_invalid_address_raises(
    db_session: AsyncSession,
) -> None:
    with pytest.raises(InvalidWarehouseError):
        await handle_create_warehouse(
            CreateWarehouseCommand(address="   ", brand="BMW"), db_session
        )


async def test_create_warehouse_unknown_city_raises(
    db_session: AsyncSession,
) -> None:
    with pytest.raises(CityNotFoundError):
        await handle_create_warehouse(
            CreateWarehouseCommand(
                address="addr", brand="BMW", city_id=uuid4()
            ),
            db_session,
        )


async def test_create_warehouse_unknown_dealer_raises(
    db_session: AsyncSession,
) -> None:
    with pytest.raises(DealerNotFoundError):
        await handle_create_warehouse(
            CreateWarehouseCommand(
                address="addr", brand="BMW", dealer_id=uuid4()
            ),
            db_session,
        )


async def test_create_warehouse_persists_with_company(
    db_session: AsyncSession,
    dealer_company: Company,
    dealer_user: User,
) -> None:
    warehouse = await handle_create_warehouse(
        CreateWarehouseCommand(
            address="ул. Тверская, 2",
            brand="Audi",
            company_id=dealer_company.id,
        ),
        db_session,
    )
    assert warehouse["id"] is not None
    assert str(warehouse["company_id"]) == str(dealer_company.id)
    assert warehouse["company_name"] == dealer_company.name
    # dealer_id auto-resolved from company
    assert str(warehouse["dealer_id"]) == str(dealer_company.id)


async def test_create_warehouse_unknown_company_raises(
    db_session: AsyncSession,
) -> None:
    from domain.errors import CompanyNotFoundError
    with pytest.raises(CompanyNotFoundError):
        await handle_create_warehouse(
            CreateWarehouseCommand(
                address="addr", brand="BMW", company_id=uuid4()
            ),
            db_session,
        )


async def test_warehouse_hydration_uses_effective_company_name(
    db_session: AsyncSession,
) -> None:
    legacy_company = Company(
        name="Legacy warehouse company",
        company_type="dealer",
        is_active=True,
    )
    primary_company = Company(
        name="Primary warehouse company",
        company_type="dealer",
        is_active=True,
    )
    db_session.add_all([legacy_company, primary_company])
    await db_session.flush()

    legacy_warehouse = Warehouse(
        address="Legacy effective owner",
        brand="BMW",
        dealer_id=legacy_company.id,
    )
    conflicting_warehouse = Warehouse(
        address="Conflicting effective owner",
        brand="BMW",
        dealer_id=legacy_company.id,
        company_id=primary_company.id,
    )
    db_session.add_all([legacy_warehouse, conflicting_warehouse])
    await db_session.flush()

    legacy_result = await handle_get_warehouse(
        GetWarehouseQuery(warehouse_id=legacy_warehouse.id), db_session
    )
    conflicting_result = await handle_get_warehouse(
        GetWarehouseQuery(warehouse_id=conflicting_warehouse.id), db_session
    )

    assert legacy_result["company_name"] == legacy_company.name
    assert legacy_result["dealer_name"] == legacy_company.name
    assert conflicting_result["company_name"] == primary_company.name
    assert conflicting_result["dealer_name"] == legacy_company.name


async def test_update_warehouse_replaces_address(
    db_session: AsyncSession,
) -> None:
    created = await handle_create_warehouse(
        CreateWarehouseCommand(address="orig", brand="BMW"), db_session
    )
    updated = await handle_update_warehouse(
        UpdateWarehouseCommand(
            warehouse_id=created["id"], address="renamed"
        ),
        db_session,
    )
    assert updated["address"] == "renamed"
    assert updated["brand"] == "BMW"


async def test_update_warehouse_missing_raises(
    db_session: AsyncSession,
) -> None:
    with pytest.raises(WarehouseNotFoundError):
        await handle_update_warehouse(
            UpdateWarehouseCommand(warehouse_id=uuid4(), address="x"),
            db_session,
        )


async def test_delete_warehouse_removes_row(
    db_session: AsyncSession,
) -> None:
    created = await handle_create_warehouse(
        CreateWarehouseCommand(address="del", brand="BMW"), db_session
    )
    await handle_delete_warehouse(
        DeleteWarehouseCommand(warehouse_id=created["id"]), db_session
    )
    with pytest.raises(WarehouseNotFoundError):
        await handle_get_warehouse(
            GetWarehouseQuery(warehouse_id=created["id"]), db_session
        )


async def test_delete_warehouse_missing_raises(
    db_session: AsyncSession,
) -> None:
    with pytest.raises(WarehouseNotFoundError):
        await handle_delete_warehouse(
            DeleteWarehouseCommand(warehouse_id=uuid4()), db_session
        )


async def test_list_warehouses_pagination(db_session: AsyncSession) -> None:
    for i in range(3):
        await handle_create_warehouse(
            CreateWarehouseCommand(address=f"addr-{i}", brand="BMW"),
            db_session,
        )
    result = await handle_list_warehouses(
        ListWarehousesQuery(page=1, limit=2), db_session
    )
    assert result["pagination"]["total"] >= 3
    assert len(result["warehouses"]) == 2


# ---------------------------------------------------------------------------
# Vehicle ↔ warehouse bindings
# ---------------------------------------------------------------------------


async def test_add_vehicle_to_warehouse_happy_path(
    db_session: AsyncSession,
    vehicle_bmw: Vehicle,
) -> None:
    warehouse = await handle_create_warehouse(
        CreateWarehouseCommand(address="bind", brand="BMW"), db_session
    )
    result = await handle_add_vehicle_to_warehouse(
        AddVehicleToWarehouseCommand(
            warehouse_id=warehouse["id"], vehicle_id=vehicle_bmw.id
        ),
        db_session,
    )
    assert str(result["vehicle_id"]) == str(vehicle_bmw.id)
    assert str(result["warehouse_id"]) == str(warehouse["id"])


async def test_add_vehicle_already_bound_raises(
    db_session: AsyncSession,
    vehicle_bmw: Vehicle,
) -> None:
    warehouse = await handle_create_warehouse(
        CreateWarehouseCommand(address="bind", brand="BMW"), db_session
    )
    await handle_add_vehicle_to_warehouse(
        AddVehicleToWarehouseCommand(
            warehouse_id=warehouse["id"], vehicle_id=vehicle_bmw.id
        ),
        db_session,
    )
    with pytest.raises(VehicleAlreadyInWarehouseError):
        await handle_add_vehicle_to_warehouse(
            AddVehicleToWarehouseCommand(
                warehouse_id=warehouse["id"], vehicle_id=vehicle_bmw.id
            ),
            db_session,
        )


async def test_add_vehicle_unknown_warehouse_raises(
    db_session: AsyncSession,
    vehicle_bmw: Vehicle,
) -> None:
    with pytest.raises(WarehouseNotFoundError):
        await handle_add_vehicle_to_warehouse(
            AddVehicleToWarehouseCommand(
                warehouse_id=uuid4(), vehicle_id=vehicle_bmw.id
            ),
            db_session,
        )


async def test_add_vehicle_unknown_vehicle_raises(
    db_session: AsyncSession,
) -> None:
    warehouse = await handle_create_warehouse(
        CreateWarehouseCommand(address="bind", brand="BMW"), db_session
    )
    with pytest.raises(VehicleNotFoundError):
        await handle_add_vehicle_to_warehouse(
            AddVehicleToWarehouseCommand(
                warehouse_id=warehouse["id"], vehicle_id=uuid4()
            ),
            db_session,
        )


async def test_remove_vehicle_happy_path(
    db_session: AsyncSession,
    vehicle_bmw: Vehicle,
) -> None:
    warehouse = await handle_create_warehouse(
        CreateWarehouseCommand(address="bind", brand="BMW"), db_session
    )
    await handle_add_vehicle_to_warehouse(
        AddVehicleToWarehouseCommand(
            warehouse_id=warehouse["id"], vehicle_id=vehicle_bmw.id
        ),
        db_session,
    )
    await handle_remove_vehicle_from_warehouse(
        RemoveVehicleFromWarehouseCommand(
            warehouse_id=warehouse["id"], vehicle_id=vehicle_bmw.id
        ),
        db_session,
    )
    listing = await handle_list_warehouse_vehicles(
        ListWarehouseVehiclesQuery(warehouse_id=warehouse["id"]), db_session
    )
    assert listing["pagination"]["total"] == 0


async def test_remove_vehicle_missing_binding_raises(
    db_session: AsyncSession,
    vehicle_bmw: Vehicle,
) -> None:
    warehouse = await handle_create_warehouse(
        CreateWarehouseCommand(address="bind", brand="BMW"), db_session
    )
    with pytest.raises(VehicleNotInWarehouseError):
        await handle_remove_vehicle_from_warehouse(
            RemoveVehicleFromWarehouseCommand(
                warehouse_id=warehouse["id"], vehicle_id=vehicle_bmw.id
            ),
            db_session,
        )


async def test_bind_by_mark_attaches_unbound_vehicles(
    db_session: AsyncSession,
    mark_bmw: Mark,
) -> None:
    warehouse = await handle_create_warehouse(
        CreateWarehouseCommand(address="bind", brand="BMW"), db_session
    )

    v1 = Vehicle(mark_id=mark_bmw.id, vin="VIN_BIND_1", status="available")
    v2 = Vehicle(mark_id=mark_bmw.id, vin="VIN_BIND_2", status="available")
    db_session.add_all([v1, v2])
    await db_session.flush()

    result = await handle_bind_vehicles_by_mark(
        BindVehiclesByMarkCommand(
            warehouse_id=warehouse["id"], mark_id=mark_bmw.id
        ),
        db_session,
    )
    assert result["bound_count"] == 2
    listing = await handle_list_warehouse_vehicles(
        ListWarehouseVehiclesQuery(warehouse_id=warehouse["id"]), db_session
    )
    assert listing["pagination"]["total"] == 2


async def test_bind_by_mark_unknown_mark_raises(
    db_session: AsyncSession,
) -> None:
    warehouse = await handle_create_warehouse(
        CreateWarehouseCommand(address="bind", brand="BMW"), db_session
    )
    with pytest.raises(MarkNotFoundError):
        await handle_bind_vehicles_by_mark(
            BindVehiclesByMarkCommand(
                warehouse_id=warehouse["id"], mark_id="not_a_real_mark"
            ),
            db_session,
        )
