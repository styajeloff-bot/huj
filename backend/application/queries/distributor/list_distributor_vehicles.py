"""List vehicles within the distributor's scope."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.distributor_scope import resolve_distributor_scope
from infrastructure.repositories import distributor_repository as repo


@dataclass
class ListDistributorVehiclesQuery:
    actor_id: UUID
    actor_role: str
    company_id: UUID | None = None
    page: int = 1
    limit: int = 20
    status: str | None = None
    search: str | None = None
    sort_by: str = "created_at"
    sort_order: str = "desc"


async def handle_list_distributor_vehicles(
    query: ListDistributorVehiclesQuery, session: AsyncSession
) -> dict[str, Any]:
    scope = await resolve_distributor_scope(
        session,
        actor_id=query.actor_id, actor_role=query.actor_role, company_id=query.company_id
    )
    items, total = await repo.list_distributor_vehicles(
        session,
        dealer_filter=scope.dealer_filter(),
        page=query.page,
        limit=query.limit,
        status=query.status,
        search=query.search,
        sort_by=query.sort_by,
        sort_order=query.sort_order,
    )
    pages = math.ceil(total / query.limit) if query.limit > 0 else 0
    return {
        "vehicles": items,
        "pagination": {
            "page": query.page,
            "limit": query.limit,
            "total": total,
            "pages": pages,
        },
    }
