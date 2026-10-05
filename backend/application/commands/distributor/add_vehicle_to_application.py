"""Attach a distributor vehicle to a leasing application."""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.distributor_scope import resolve_distributor_scope
from domain.errors import (
    ApplicationNotFoundError,
    VehicleNotAvailableError,
    VehicleNotFoundError,
)
from infrastructure.repositories import application_repository as app_repo
from infrastructure.repositories import distributor_repository as repo


@dataclass
class AddVehicleToApplicationCommand:
    actor_id: UUID
    actor_role: str
    application_id: uuid.UUID
    vehicle_id: UUID
    quantity: int = 1
    company_id: UUID | None = None


async def handle_add_vehicle_to_application(
    cmd: AddVehicleToApplicationCommand, session: AsyncSession
) -> dict[str, Any]:
    from infrastructure.repositories import (
        vehicle_fulfillment_repository as fulfillment,
    )
    await fulfillment.stock(session, [cmd.vehicle_id], lock=True)
    scope = await resolve_distributor_scope(
        session,
        actor_id=cmd.actor_id, actor_role=cmd.actor_role, company_id=cmd.company_id
    )

    application = await app_repo.get_by_id(
        session, cmd.application_id
    )
    if application is None:
        raise ApplicationNotFoundError(cmd.application_id)

    vehicle = await repo.get_distributor_vehicle(session, cmd.vehicle_id)
    if vehicle is None:
        raise VehicleNotFoundError(cmd.vehicle_id)
    scope.ensure_can_write(vehicle.get("dealer_id"))
    if vehicle.get("status") != "available":
        raise VehicleNotAvailableError(cmd.vehicle_id)

    base_price = vehicle.get("base_price") or Decimal("0")
    if not isinstance(base_price, Decimal):
        base_price = Decimal(str(base_price))
    total_price = base_price * Decimal(cmd.quantity)

    new_id = await repo.add_vehicle_to_application(
        session,
        application_id=cmd.application_id,
        vehicle_id=cmd.vehicle_id,
        quantity=max(1, cmd.quantity),
        unit_price=base_price,
        total_price=total_price,
    )
    await repo.set_vehicle_status(
        session, vehicle_id=cmd.vehicle_id, status="reserved"
    )
    from infrastructure.messaging.dwh_events import emit_app_vehicle_changed
    emit_app_vehicle_changed({
        "id": new_id,
        "application_id": str(cmd.application_id),
        "vehicle_id": cmd.vehicle_id,
        "modification_id": None,
        "quantity": max(1, cmd.quantity),
        "unit_price": str(base_price),
        "total_price": str(total_price),
        "comment": None,
        "vin": None,
        "vin_assigned_by": None,
        "vin_assigned_at": None,
        "is_model_order": 0,
        "created_at": None,
        "updated_at": None,
        "_deleted": False,
    })
    return {
        "id": new_id,
        "application_id": cmd.application_id,
        "vehicle_id": cmd.vehicle_id,
        "message": "Автомобиль добавлен в заявку",
    }
