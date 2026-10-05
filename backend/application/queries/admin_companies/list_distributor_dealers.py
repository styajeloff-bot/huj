"""Admin query: list dealers linked to a distributor company."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.repositories import distributor_dealer_repository as repo


@dataclass(frozen=True)
class ListDistributorDealersQuery:
    distributor_company_id: UUID
    page: int = 1
    limit: int = 20


async def handle_list_distributor_dealers(
    query: ListDistributorDealersQuery, session: AsyncSession
) -> dict[str, Any]:
    items, total = await repo.list_dealers_for_distributor(
        session,
        distributor_company_id=query.distributor_company_id,
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
