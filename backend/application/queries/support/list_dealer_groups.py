"""List dealer groups (admin)."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.repositories import dealer_group_repository as repo


@dataclass
class ListDealerGroupsQuery:
    page: int = 1
    limit: int = 20
    search: str | None = None
    distributor_id: UUID | None = None
    dealer_id: UUID | None = None
    is_active: bool | None = None


async def handle_list_dealer_groups(
    query: ListDealerGroupsQuery, session: AsyncSession
) -> dict[str, Any]:
    items, total = await repo.list_dealer_groups(
        session,
        page=query.page,
        limit=query.limit,
        search=query.search,
        distributor_id=query.distributor_id,
        dealer_id=query.dealer_id,
        is_active=query.is_active,
    )
    pages = math.ceil(total / query.limit) if query.limit > 0 else 0
    return {
        "dealer_groups": items,
        "pagination": {
            "page": query.page,
            "limit": query.limit,
            "total": total,
            "pages": pages,
        },
    }
