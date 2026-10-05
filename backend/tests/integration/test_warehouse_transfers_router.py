"""Integration tests for the warehouse-transfer HTTP API."""
from __future__ import annotations

from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.auth import generate_tokens
from infrastructure.models.users import User
from infrastructure.models.vehicles import Warehouse
from tests.legacy_compat import Vehicle, VehicleWarehouse

pytestmark = pytest.mark.asyncio

_PREFIX = "/api/v1/distributor/warehouse-transfers"


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def test_transfer_router_lists_source_vehicles_and_moves_selection(
    client: AsyncClient,
    db_session: AsyncSession,
    employee_token: str,
) -> None:
    source = Warehouse(address="Исходный склад", brand="BMW")
    destination = Warehouse(address="Целевой склад", brand="BMW")
    vehicle = Vehicle(vin="HTTP-TRANSFER-OK", status="available", is_available=True)
    db_session.add_all([source, destination, vehicle])
    await db_session.flush()
    db_session.add(VehicleWarehouse(vehicle_id=vehicle.id, warehouse_id=source.id))
    await db_session.flush()

    warehouses = await client.get(f"{_PREFIX}/warehouses", headers=_auth(employee_token))
    assert warehouses.status_code == 200
    assert {item["id"] for item in warehouses.json()["warehouses"]} >= {
        str(source.id),
        str(destination.id),
    }

    vehicles = await client.get(
        f"{_PREFIX}/vehicles",
        params={"source_warehouse_id": str(source.id)},
        headers=_auth(employee_token),
    )
    assert vehicles.status_code == 200
    assert vehicles.json()["pagination"]["total"] == 1
    assert vehicles.json()["vehicles"][0]["id"] == str(vehicle.id)

    transfer = await client.post(
        f"{_PREFIX}",
        json={
            "source_warehouse_id": source.id,
            "destination_warehouse_id": destination.id,
            "vehicle_ids": [vehicle.id],
        },
        headers=_auth(employee_token),
    )
    assert transfer.status_code == 201
    assert transfer.json() == {
        "transferred_count": 1,
        "failed_count": 0,
        "results": [{"vehicle_id": str(vehicle.id), "status": "transferred"}],
        "message": "Автомобили успешно перемещены",
    }


async def test_transfer_router_returns_russian_400_for_business_validation(
    client: AsyncClient,
    employee_token: str,
) -> None:
    warehouse_id = uuid4()
    response = await client.post(
        f"{_PREFIX}",
        json={
            "source_warehouse_id": warehouse_id,
            "destination_warehouse_id": warehouse_id,
            "vehicle_ids": [uuid4()],
        },
        headers=_auth(employee_token),
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Исходный и целевой склады должны отличаться"


async def test_transfer_router_returns_400_when_selection_mode_is_missing(
    client: AsyncClient,
    db_session: AsyncSession,
    employee_token: str,
) -> None:
    source = Warehouse(address="Склад без выбора", brand="BMW")
    destination = Warehouse(address="Другой склад без выбора", brand="BMW")
    db_session.add_all([source, destination])
    await db_session.flush()

    response = await client.post(
        f"{_PREFIX}",
        json={
            "source_warehouse_id": source.id,
            "destination_warehouse_id": destination.id,
        },
        headers=_auth(employee_token),
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Необходимо выбрать хотя бы один автомобиль"


async def test_transfer_router_rejects_dealer_role(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    dealer = User(
        phone="+766****2174",
        email="warehouse-transfer-dealer@test.local",
        name="Dealer without transfer access",
        role="dealer",
        is_active=True,
    )
    db_session.add(dealer)
    await db_session.flush()
    token, _ = generate_tokens(dealer.id, dealer.role, dealer.company_id)

    response = await client.get(f"{_PREFIX}/warehouses", headers=_auth(token))
    assert response.status_code == 403


async def test_transfer_router_requires_vehicle_admin_scope(client: AsyncClient) -> None:
    response = await client.get(f"{_PREFIX}/warehouses")
    assert response.status_code == 401
