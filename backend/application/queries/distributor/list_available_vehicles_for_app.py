"""List available vehicles the distributor may attach to an application."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.distributor_scope import resolve_distributor_scope
from infrastructure.repositories import distributor_repository as repo


@dataclass
class ListAvailableVehiclesForAppQuery:
    actor_id: UUID
    actor_role: str
    company_id: UUID | None = None
    mark_id: str | None = None
    model_id: str | None = None
    limit: int = 100


async def handle_list_available_vehicles_for_app(
    query: ListAvailableVehiclesForAppQuery, session: AsyncSession
) -> dict[str, Any]:
    scope = await resolve_distributor_scope(
        session,
        actor_id=query.actor_id, actor_role=query.actor_role, company_id=query.company_id
    )
    vehicles = await repo.list_available_vehicles_for_app(
        session,
        dealer_filter=scope.dealer_filter(),
        mark_id=query.mark_id,
        model_id=query.model_id,
        limit=query.limit,
    )
    return {"vehicles": vehicles}
