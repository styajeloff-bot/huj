"""Dealers visible to the distributor (or all dealers for employees)."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.distributor_scope import resolve_distributor_scope
from infrastructure.repositories import distributor_repository as repo


@dataclass
class ListDistributorDealersQuery:
    actor_id: UUID
    actor_role: str
    company_id: UUID | None = None
    page: int = 1
    limit: int = 20


async def handle_list_distributor_dealers(
    query: ListDistributorDealersQuery, session: AsyncSession
) -> dict[str, Any]:
    scope = await resolve_distributor_scope(
        session,
        actor_id=query.actor_id, actor_role=query.actor_role, company_id=query.company_id
    )
    items, total = await repo.list_distributor_dealers(
        session,
        dealer_filter=scope.dealer_filter(),
        page=query.page,
        limit=query.limit,
    )
    pages = math.ceil(total / query.limit) if query.limit > 0 else 0
    return {
        "dealers": items,
        "pagination": {
            "page": query.page,
            "limit": query.limit,
            "total": total,
            "pages": pages,
        },
    }
