"""List warehouses within the requesting actor's read scope."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.warehouse_scope import resolve_warehouse_dealer_filter
from domain.values import WarehouseStatus
from infrastructure.repositories import warehouse_repository as repo


@dataclass
class ListWarehousesQuery:
    page: int = 1
    limit: int = 20
    search: str | None = None
    brand: str | None = None
    brand_id: UUID | None = None
    city_id: UUID | None = None
    access_type: str | None = None
    owner_company_id: UUID | None = None
    is_active: bool | None = None
    status: WarehouseStatus | None = None
    actor_id: UUID | None = None
    actor_role: str = "carcraft_employee"
    company_id: UUID | None = None


async def handle_list_warehouses(
    query: ListWarehousesQuery, session: AsyncSession
) -> dict[str, Any]:
    dealer_filter = await resolve_warehouse_dealer_filter(
        session,
        actor_id=query.actor_id or UUID(int=0),
        actor_role=query.actor_role,
        company_id=query.company_id,
    )
    items, total = await repo.list_warehouses(
        session,
        page=query.page,
        limit=query.limit,
        search=query.search,
        brand=query.brand,
        brand_id=query.brand_id,
        city_id=query.city_id,
        access_type=query.access_type,
        owner_company_id=query.owner_company_id,
        is_active=query.is_active,
        status=query.status,
        dealer_filter=dealer_filter,
        company_id=query.company_id,
        actor_role=query.actor_role,
    )
    pages = math.ceil(total / query.limit) if query.limit > 0 else 0
    return {
        "warehouses": items,
        "pagination": {
            "page": query.page,
            "limit": query.limit,
            "total": total,
            "pages": pages,
        },
    }
