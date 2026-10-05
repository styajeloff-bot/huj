"""List vehicles in a warehouse within the requesting actor's read scope."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.warehouse_scope import resolve_warehouse_dealer_filter
from domain.errors import WarehouseNotFoundError
from infrastructure.repositories import warehouse_repository as repo


@dataclass
class ListWarehouseVehiclesQuery:
    warehouse_id: UUID
    page: int = 1
    limit: int = 20
    actor_id: UUID | None = None
    actor_role: str = "carcraft_employee"
    company_id: UUID | None = None
    status: str | None = None


async def handle_list_warehouse_vehicles(
    query: ListWarehouseVehiclesQuery, session: AsyncSession
) -> dict[str, Any]:
    dealer_filter = await resolve_warehouse_dealer_filter(
        session,
        actor_id=query.actor_id or UUID(int=0),
        actor_role=query.actor_role,
        company_id=query.company_id,
    )
    if await repo.get_by_id(
        session,
        query.warehouse_id,
        dealer_filter=dealer_filter,
    ) is None:
        raise WarehouseNotFoundError(query.warehouse_id)

    items, total = await repo.list_warehouse_vehicles(
        session,
        query.warehouse_id,
        page=query.page,
        limit=query.limit,
        status=query.status,
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
