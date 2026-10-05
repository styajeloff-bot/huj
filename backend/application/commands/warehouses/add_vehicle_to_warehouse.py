"""Bind a vehicle to a warehouse."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from domain.errors import (
    VehicleAlreadyInWarehouseError,
    VehicleNotFoundError,
    WarehouseNotFoundError,
)
from infrastructure.repositories import warehouse_repository as repo


@dataclass
class AddVehicleToWarehouseCommand:
    warehouse_id: UUID
    vehicle_id: UUID


async def handle_add_vehicle_to_warehouse(
    cmd: AddVehicleToWarehouseCommand, session: AsyncSession
) -> dict[str, Any]:
    if await repo.get_by_id(session, cmd.warehouse_id) is None:
        raise WarehouseNotFoundError(cmd.warehouse_id)

    if not await repo.vehicle_exists(session, cmd.vehicle_id):
        raise VehicleNotFoundError(cmd.vehicle_id)

    binding = await repo.get_binding(session, cmd.vehicle_id)
    if binding is not None:
        raise VehicleAlreadyInWarehouseError(
            cmd.vehicle_id, binding["warehouse_id"]
        )

    try:
        created = await repo.create_binding(
            session, vehicle_id=cmd.vehicle_id, warehouse_id=cmd.warehouse_id
        )
    except repo.WarehouseBindingTargetUnavailableError as exc:
        raise WarehouseNotFoundError(cmd.warehouse_id) from exc
    if not created:
        # Race with a concurrent insert — surface as conflict.
        raise VehicleAlreadyInWarehouseError(cmd.vehicle_id)

    return {
        "message": "Автомобиль успешно привязан к складу",
        "vehicle_id": cmd.vehicle_id,
        "warehouse_id": cmd.warehouse_id,
    }
