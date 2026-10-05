"""Batch-read vehicles by a list of ids within the distributor's scope."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.distributor_scope import resolve_distributor_scope
from domain.errors import VehicleNotFoundError
from infrastructure.repositories import distributor_repository as repo


@dataclass
@dataclass
class GetDistributorVehiclesByIdsQuery:
    actor_id: UUID
    actor_role: str
    vehicle_ids: list[UUID] = field(default_factory=list)
    company_id: UUID | None = None


async def handle_get_distributor_vehicles_by_ids(
    query: GetDistributorVehiclesByIdsQuery, session: AsyncSession
) -> dict[str, Any]:
    scope = await resolve_distributor_scope(
        session,
        actor_id=query.actor_id, actor_role=query.actor_role,
        company_id=query.company_id
    )
    items: list[dict[str, Any]] = []
    for vid in query.vehicle_ids:
        row = await repo.get_distributor_vehicle(session, vid)
        if row is None:
            raise VehicleNotFoundError(vid)
        scope.ensure_can_write(row.get("dealer_id"))
        items.append(row)
    return {
        "vehicles": items,
        "pagination": {
            "page": 1,
            "limit": len(items),
            "total": len(items),
            "pages": 1,
        },
    }
