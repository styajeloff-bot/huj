"""List SOPD contractors for the admin contractors catalog."""
from __future__ import annotations

import math
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.repositories import contractors_repository as repo


@dataclass(frozen=True)
class ListContractorsQuery:
    page: int
    limit: int
    contractor_name: str | None = None
    inn: str | None = None


async def handle_list_contractors(
    query: ListContractorsQuery, session: AsyncSession
) -> dict[str, object]:
    items, total = await repo.list_contractors(
        session,
        page=query.page,
        limit=query.limit,
        contractor_name=query.contractor_name,
        inn=query.inn,
    )
    return {
        "items": items,
        "pagination": {
            "page": query.page,
            "limit": query.limit,
            "total": total,
            "pages": math.ceil(total / query.limit) if total else 0,
        },
    }
