"""Bind a selected set of currently unbound vehicles to a warehouse."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from domain.errors import VehicleNotFoundError, WarehouseNotFoundError
from infrastructure.repositories import warehouse_repository as repo


@dataclass
class BulkAddVehiclesToWarehouseCommand:
    warehouse_id: UUID
    vehicle_ids: list[UUID]


async def handle_bulk_add_vehicles_to_warehouse(
    cmd: BulkAddVehiclesToWarehouseCommand, session: AsyncSession
) -> dict[str, Any]:
    if await repo.get_by_id(session, cmd.warehouse_id) is None:
        raise WarehouseNotFoundError(cmd.warehouse_id)

    existing_vehicle_ids = await repo.get_existing_vehicle_ids(session, cmd.vehicle_ids)
    for vehicle_id in cmd.vehicle_ids:
        if vehicle_id not in existing_vehicle_ids:
            raise VehicleNotFoundError(vehicle_id)

    bound = await repo.bulk_create_unbound_bindings(
        session, warehouse_id=cmd.warehouse_id, vehicle_ids=cmd.vehicle_ids
    )
    return {"bound": bound, "skipped": len(cmd.vehicle_ids) - bound}
