"""Assign a vehicle (dealer) to an application_vehicles row."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from domain.errors import (
    ApplicationVehicleAssignmentError,
    ApplicationVehicleNotFoundError,
    DealerNotFoundError,
    VehicleNotFoundError,
)
from infrastructure.repositories import (
    application_vehicle_repository as repo,
)


@dataclass
class AssignVehicleCommand:
    application_vehicle_id: UUID
    actor_id: UUID
    dealer_id: UUID | None = None


async def handle_assign_vehicle(
    cmd: AssignVehicleCommand, session: AsyncSession
) -> dict[str, Any]:
    av = await repo.get_by_id(session, cmd.application_vehicle_id)
    if av is None:
        raise ApplicationVehicleNotFoundError(cmd.application_vehicle_id)

    if av.get("vehicle_id") is None:
        raise ApplicationVehicleAssignmentError(
            "У записи нет привязанного автомобиля; "
            "сначала назначьте VIN или vehicle_id"
        )
    if cmd.dealer_id is None:
        raise ApplicationVehicleAssignmentError(
            "Необходимо указать dealer_id"
        )
    try:
        ok = await repo.update_vehicle_dealer(
            session,
            av["vehicle_id"],
            dealer_id=cmd.dealer_id,
        )
    except IntegrityError as exc:
        raise DealerNotFoundError(cmd.dealer_id) from exc

    if not ok:
        raise VehicleNotFoundError(av["vehicle_id"])

    return {
        "success": True,
        "message": "Автомобиль назначен",
        "application_vehicle_id": cmd.application_vehicle_id,
    }
