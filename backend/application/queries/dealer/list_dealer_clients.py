"""Query: list clients created through the dealer invite funnel.

Clients are derived from leasing applications owned by this dealer's
company — the mapping is via ``dealer_company_id`` / ``company_id``."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.repositories import dealer_repository as repo


@dataclass(frozen=True)
class ListDealerClientsQuery:
    dealer_id: UUID
    search: str | None = None
    is_active: bool | None = None
    page: int = 1
    limit: int = 20


async def handle_list_dealer_clients(
    query: ListDealerClientsQuery, session: AsyncSession
) -> dict[str, Any]:
    items, total = await repo.list_dealer_clients(
        session,
        query.dealer_id,
        search=query.search,
        is_active=query.is_active,
        page=query.page,
        limit=query.limit,
    )
    pages = math.ceil(total / query.limit) if query.limit > 0 else 0
    return {
        "clients": items,
        "pagination": {
            "page": query.page,
            "limit": query.limit,
            "total": total,
            "pages": pages,
        },
    }
