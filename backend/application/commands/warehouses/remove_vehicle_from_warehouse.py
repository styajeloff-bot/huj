"""Remove a vehicle binding from a warehouse."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from domain.errors import (
    VehicleNotInWarehouseError,
    WarehouseNotFoundError,
)
from infrastructure.repositories import warehouse_repository as repo


@dataclass
class RemoveVehicleFromWarehouseCommand:
    warehouse_id: UUID
    vehicle_id: UUID


async def handle_remove_vehicle_from_warehouse(
    cmd: RemoveVehicleFromWarehouseCommand, session: AsyncSession
) -> dict[str, Any]:
    if await repo.get_by_id(session, cmd.warehouse_id) is None:
        raise WarehouseNotFoundError(cmd.warehouse_id)

    deleted = await repo.delete_binding(
        session,
        warehouse_id=cmd.warehouse_id,
        vehicle_id=cmd.vehicle_id,
    )
    if not deleted:
        raise VehicleNotInWarehouseError(cmd.vehicle_id)

    return {"message": "Автомобиль отвязан от склада"}
