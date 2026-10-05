"""List scoped vehicles from a warehouse-transfer source warehouse."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.distributor_scope import resolve_distributor_scope
from infrastructure.repositories import warehouse_repository as repository


@dataclass(frozen=True)
class ListSourceVehiclesQuery:
    actor_id: UUID
    actor_role: str
    source_warehouse_id: UUID
    company_id: UUID | None = None
    page: int = 1
    limit: int = 20
    vin: str | None = None
    mark_ids: list[str] | None = None
    model_ids: list[str] | None = None
    years: list[int] | None = None
    colors: list[str] | None = None


async def handle_list_source_vehicles(
    query: ListSourceVehiclesQuery,
    session: AsyncSession,
) -> dict[str, Any]:
    scope = await resolve_distributor_scope(
        session,
        actor_id=query.actor_id,
        actor_role=query.actor_role,
        company_id=query.company_id,
    )
    vehicles, total, facets = await repository.list_source_warehouse_vehicles(
        session,
        source_warehouse_id=query.source_warehouse_id,
        dealer_filter=scope.dealer_filter(),
        page=query.page,
        limit=query.limit,
        vin=query.vin,
        mark_ids=query.mark_ids,
        model_ids=query.model_ids,
        years=query.years,
        colors=query.colors,
    )
    return {
        "vehicles": vehicles,
        "facets": facets,
        "pagination": {
            "page": query.page,
            "limit": query.limit,
            "total": total,
            "pages": math.ceil(total / query.limit) if query.limit else 0,
        },
    }
