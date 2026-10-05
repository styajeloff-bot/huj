"""Delete a vehicle that belongs to the distributor's scope."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.distributor_scope import resolve_distributor_scope
from domain.errors import VehicleNotFoundError
from infrastructure.repositories import distributor_repository as repo


@dataclass
class DeleteDistributorVehicleCommand:
    vehicle_id: UUID
    actor_id: UUID
    actor_role: str
    company_id: UUID | None = None


async def handle_delete_distributor_vehicle(
    cmd: DeleteDistributorVehicleCommand, session: AsyncSession
) -> dict[str, Any]:
    scope = await resolve_distributor_scope(
        session,
        actor_id=cmd.actor_id, actor_role=cmd.actor_role, company_id=cmd.company_id
    )
    existing = await repo.get_distributor_vehicle(session, cmd.vehicle_id)
    if existing is None:
        raise VehicleNotFoundError(cmd.vehicle_id)
    scope.ensure_can_write(existing.get("dealer_id"))

    deleted = await repo.delete_vehicle_in_scope(
        session,
        vehicle_id=cmd.vehicle_id,
        dealer_filter=scope.dealer_filter(),
    )
    if not deleted:
        raise VehicleNotFoundError(cmd.vehicle_id)
    return {"message": "Автомобиль удалён", "id": cmd.vehicle_id}
