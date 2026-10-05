"""Administrative vehicle deletion and bulk warehouse unbinding."""
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.errors import ServiceError
from domain.vehicle_deletion import (
    BlockingReason,
    VehicleDeletionBlockedError,
    VehicleDeletionPolicy,
    confirmation_matches,
)
from infrastructure.repositories import vehicle_deletion_repository as repo


class VehicleDeletionError(ServiceError):
    def __init__(
        self, code: str, message: str, status_code: int = 400,
        *, blocking_reasons: list[BlockingReason] | None = None,
    ) -> None:
        super().__init__(message, status_code, code=code)
        self.blocking_reasons = blocking_reasons


async def require_warehouse(session: AsyncSession, warehouse_id: UUID) -> None:
    if not await repo.warehouse_exists(session, warehouse_id):
        raise VehicleDeletionError("warehouse_not_found", "Склад не найден", 404)


def require_confirmation(confirmation: str | None, vin: str = "") -> None:
    if not confirmation_matches(confirmation, vin):
        raise VehicleDeletionError("confirmation_mismatch", "Неверное подтверждение удаления")


def require_confirmed(confirmed: bool) -> None:
    if not confirmed:
        raise VehicleDeletionError("confirmation_required", "Необходимо подтвердить операцию")


async def handle_admin_delete_vehicle(
    session: AsyncSession, vehicle_id: UUID, confirmation: str | None,
) -> dict[str, Any]:
    await repo.lock_bindings(session)
    vehicles = await repo.get_vehicles(session, vehicle_id=vehicle_id, lock=True)
    if not vehicles:
        raise VehicleDeletionError("vehicle_not_found", "Автомобиль не найден", 404)
    vehicle = vehicles[0]
    require_confirmation(confirmation, vehicle["vin"])
    blockers = (await repo.blocking_reasons(session, [vehicle_id]))[vehicle_id]
    try:
        VehicleDeletionPolicy(tuple(blockers)).assert_allowed()
    except VehicleDeletionBlockedError as exc:
        raise VehicleDeletionError(
            "vehicle_has_blocking_relations", str(exc), 409,
            blocking_reasons=exc.blocking_reasons,
        ) from exc
    cleaned = await repo.delete_checked_vehicle(session, vehicle)
    await repo.invalidate_catalog(session)
    return {"deleted": True, "vehicle_id": vehicle_id, "cleaned_relations": cleaned}


async def handle_unbind_all_warehouse_vehicles(
    session: AsyncSession, warehouse_id: UUID, confirmed: bool,
) -> dict[str, Any]:
    require_confirmed(confirmed)
    await repo.lock_bindings(session)
    await require_warehouse(session, warehouse_id)
    from domain.errors import ApplicationVehicleAssignmentError
    try:
        count = await repo.unbind_warehouse(session, warehouse_id)
    except ApplicationVehicleAssignmentError as exc:
        raise VehicleDeletionError("vehicles_reserved", str(exc), 409) from exc
    return {"warehouse_id": warehouse_id, "unbound_count": count}


async def handle_bulk_delete_warehouse_vehicles(
    session: AsyncSession, warehouse_id: UUID, confirmed: bool, confirmation: str | None,
) -> dict[str, Any]:
    require_confirmed(confirmed)
    require_confirmation(confirmation)
    await repo.lock_bindings(session)
    await require_warehouse(session, warehouse_id)
    vehicles = await repo.get_vehicles(session, warehouse_id=warehouse_id, lock=True)
    blockers = await repo.blocking_reasons(session, [v["id"] for v in vehicles])
    skipped = []
    deleted_count = 0
    for vehicle in vehicles:
        reasons = blockers[vehicle["id"]]
        if not VehicleDeletionPolicy(tuple(reasons)).can_delete:
            skipped.append({"vehicle_id": vehicle["id"], "vin": vehicle["vin"], "blocking_reasons": reasons})
        else:
            await repo.delete_checked_vehicle(session, vehicle)
            deleted_count += 1
    if deleted_count:
        await repo.invalidate_catalog(session)
    return {
        "warehouse_id": warehouse_id, "requested_count": len(vehicles),
        "deleted_count": deleted_count, "skipped_count": len(skipped), "skipped": skipped,
    }
