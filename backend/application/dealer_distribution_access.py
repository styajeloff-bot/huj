"""Protect existing whole-line mutations from partial dealer assignments."""

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from domain.dealer_distribution_access import (
    can_manage_whole_vehicle,
    ensure_whole_vehicle_write,
)
from domain.errors import ApplicationVehicleNotFoundError
from infrastructure.repositories import dealer_distribution_access_repository as repo


async def ensure_whole_vehicle_write_allowed(
    session: AsyncSession, *, application_vehicle_id: UUID,
    actor_role: str, actor_company_id: UUID | None,
    lock: bool = True,
) -> dict[str, Any]:
    scope = await repo.get_write_scope(session,
        application_vehicle_id=application_vehicle_id, actor_company_id=actor_company_id, lock=lock)
    if scope is None:
        raise ApplicationVehicleNotFoundError(application_vehicle_id)
    ensure_whole_vehicle_write(allowed=can_manage_whole_vehicle(
        actor_role=actor_role, actor_company_id=actor_company_id,
        stock_owner_id=scope["stock_owner_id"], quantity=scope["quantity"],
        distributed_quantity=scope["distributed_quantity"], actor_quantity=scope["actor_quantity"],
    ))
    return scope
