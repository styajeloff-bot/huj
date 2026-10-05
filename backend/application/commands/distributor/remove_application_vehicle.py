
"""Remove an application_vehicles row from a leasing application."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.common import _isoformat
from application.distributor_scope import resolve_distributor_scope
from domain.errors import ApplicationVehicleNotFoundError
from infrastructure.repositories import distributor_repository as repo


@dataclass
class RemoveApplicationVehicleCommand:
    actor_id: UUID
    actor_role: str
    application_vehicle_id: UUID
    company_id: UUID | None = None


async def handle_remove_application_vehicle(
    cmd: RemoveApplicationVehicleCommand, session: AsyncSession
) -> dict[str, Any]:
    from application.errors import ServiceError
    from infrastructure.repositories import (
        vehicle_fulfillment_repository as fulfillment,
    )
    await fulfillment.line(session, cmd.application_vehicle_id, lock=True)
    if await fulfillment.allocations(session, cmd.application_vehicle_id):
        raise ServiceError("Используйте подбор для изменения состава заявки", 409)
    scope = await resolve_distributor_scope(
        session,
        actor_id=cmd.actor_id, actor_role=cmd.actor_role, company_id=cmd.company_id
    )
    scoped = await repo.get_application_vehicle_with_scope(
        session,
        application_vehicle_id=cmd.application_vehicle_id,
        dealer_filter=scope.dealer_filter(),
    )
    if scoped is None:
        raise ApplicationVehicleNotFoundError(cmd.application_vehicle_id)

    # Best-effort: if the row had a vehicle, release it back to "available".
    vehicle_id = scoped.get("vehicle_id")
    await repo.delete_application_vehicle(
        session, application_vehicle_id=cmd.application_vehicle_id
    )
    if vehicle_id is not None:
        await repo.set_vehicle_status(
            session, vehicle_id=vehicle_id, status="available"
        )
    from infrastructure.messaging.dwh_events import emit_app_vehicle_changed
    emit_app_vehicle_changed({
        "id": cmd.application_vehicle_id,
        "application_id": scoped.get("application_id"),
        "vehicle_id": vehicle_id,
        "modification_id": scoped.get("modification_id"),
        "quantity": scoped.get("quantity"),
        "unit_price": str(scoped.get("unit_price")) if scoped.get("unit_price") else None,
        "total_price": str(scoped.get("total_price")) if scoped.get("total_price") else None,
        "comment": scoped.get("comment"),
        "vin": scoped.get("vin"),
        "vin_assigned_by": scoped.get("vin_assigned_by"),
        "vin_assigned_at": _isoformat(scoped.get("vin_assigned_at")),
        "is_model_order": 1 if scoped.get("is_model_order") else 0,
        "created_at": _isoformat(scoped.get("created_at")),
        "updated_at": None,
        "_deleted": True,
    })
    return {
        "message": "Автомобиль удалён из заявки",
        "id": cmd.application_vehicle_id,
    }
