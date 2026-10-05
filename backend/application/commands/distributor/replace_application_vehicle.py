
"""Replace a vehicle in an application_vehicles row."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.common import _isoformat
from application.distributor_scope import resolve_distributor_scope
from domain.errors import (
    ApplicationVehicleNotFoundError,
    VehicleNotAvailableError,
    VehicleNotFoundError,
)
from infrastructure.repositories import distributor_repository as repo


@dataclass
class ReplaceApplicationVehicleCommand:
    actor_id: UUID
    actor_role: str
    application_vehicle_id: UUID
    new_vehicle_id: UUID
    company_id: UUID | None = None


async def handle_replace_application_vehicle(
    cmd: ReplaceApplicationVehicleCommand, session: AsyncSession
) -> dict[str, Any]:
    from application.errors import ServiceError
    from infrastructure.repositories import (
        vehicle_fulfillment_repository as fulfillment,
    )
    await fulfillment.line(session, cmd.application_vehicle_id, lock=True)
    if await fulfillment.allocations(session, cmd.application_vehicle_id):
        raise ServiceError("Используйте подбор для изменения состава заявки", 409)
    await fulfillment.stock(session, [cmd.new_vehicle_id], lock=True)
    scope = await resolve_distributor_scope(
        session,
        actor_id=cmd.actor_id, actor_role=cmd.actor_role, company_id=cmd.company_id
    )

    existing = await repo.get_application_vehicle_with_scope(
        session,
        application_vehicle_id=cmd.application_vehicle_id,
        dealer_filter=scope.dealer_filter(),
    )
    if existing is None:
        raise ApplicationVehicleNotFoundError(cmd.application_vehicle_id)

    new_vehicle = await repo.get_distributor_vehicle(
        session, cmd.new_vehicle_id
    )
    if new_vehicle is None:
        raise VehicleNotFoundError(cmd.new_vehicle_id)
    scope.ensure_can_write(new_vehicle.get("dealer_id"))
    if new_vehicle.get("status") != "available":
        raise VehicleNotAvailableError(cmd.new_vehicle_id)

    await repo.replace_application_vehicle_link(
        session,
        application_vehicle_id=cmd.application_vehicle_id,
        new_vehicle_id=cmd.new_vehicle_id,
    )
    await repo.set_vehicle_status(
        session, vehicle_id=cmd.new_vehicle_id, status="reserved"
    )
    old_vehicle_id = existing.get("vehicle_id")
    if old_vehicle_id is not None and old_vehicle_id != cmd.new_vehicle_id:
        await repo.set_vehicle_status(
            session, vehicle_id=old_vehicle_id, status="available"
        )
    from infrastructure.messaging.dwh_events import emit_app_vehicle_changed
    emit_app_vehicle_changed({
        "id": cmd.application_vehicle_id,
        "application_id": existing.get("application_id"),
        "vehicle_id": cmd.new_vehicle_id,
        "modification_id": existing.get("modification_id"),
        "quantity": existing.get("quantity"),
        "unit_price": str(existing.get("unit_price")) if existing.get("unit_price") else None,
        "total_price": str(existing.get("total_price")) if existing.get("total_price") else None,
        "comment": existing.get("comment"),
        "vin": existing.get("vin"),
        "vin_assigned_by": existing.get("vin_assigned_by"),
        "vin_assigned_at": _isoformat(existing.get("vin_assigned_at")),
        "is_model_order": 1 if existing.get("is_model_order") else 0,
        "created_at": _isoformat(existing.get("created_at")),
        "updated_at": None,
        "_deleted": False,
    })
    return {
        "message": "Автомобиль заменён",
        "id": cmd.application_vehicle_id,
        "vehicle_id": cmd.new_vehicle_id,
    }
