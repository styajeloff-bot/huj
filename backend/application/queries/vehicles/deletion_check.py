"""Advisory deletion checks; mutations always repeat them under locks."""
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.commands.vehicles.admin_deletion import (
    VehicleDeletionError,
    require_warehouse,
)
from domain.vehicle_deletion import VehicleDeletionPolicy
from infrastructure.repositories import vehicle_deletion_repository as repo


async def handle_vehicle_deletion_check(session: AsyncSession, vehicle_id: UUID) -> dict[str, Any]:
    vehicles = await repo.get_vehicles(session, vehicle_id=vehicle_id)
    if not vehicles:
        raise VehicleDeletionError("vehicle_not_found", "Автомобиль не найден", 404)
    reasons = (await repo.blocking_reasons(session, [vehicle_id]))[vehicle_id]
    return {
        "can_delete": VehicleDeletionPolicy(tuple(reasons)).can_delete, "vin": vehicles[0]["vin"],
        "name": vehicles[0]["name"], "blocking_reasons": reasons,
    }


async def handle_warehouse_deletion_check(session: AsyncSession, warehouse_id: UUID) -> dict[str, Any]:
    await require_warehouse(session, warehouse_id)
    vehicles = await repo.get_vehicles(session, warehouse_id=warehouse_id)
    reasons = await repo.blocking_reasons(session, [v["id"] for v in vehicles])
    aggregated: dict[str, dict[str, Any]] = {}
    for blockers in reasons.values():
        for reason in blockers:
            entry = aggregated.setdefault(reason["type"], {
                "type": reason["type"], "count": 0, "vehicle_count": 0,
                "description": reason["description"],
            })
            entry["count"] += reason["count"]
            entry["vehicle_count"] += 1
    blocked_count = sum(
        not VehicleDeletionPolicy(tuple(value)).can_delete for value in reasons.values()
    )
    return {
        "warehouse_id": warehouse_id, "requested_count": len(vehicles),
        "deletable_count": len(vehicles) - blocked_count, "blocked_count": blocked_count,
        "blocking_reasons": list(aggregated.values()),
    }
