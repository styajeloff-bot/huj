"""List LC-contractor links for the admin contractors UI."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.repositories import contractors_repository as repo


@dataclass(frozen=True)
class ListContractorLinksQuery:
    page: int = 1
    limit: int = 20
    leasing_company_id: UUID | None = None
    contractor_name: str | None = None
    inn: str | None = None


async def handle_list_contractor_links(
    query: ListContractorLinksQuery, session: AsyncSession
) -> dict[str, Any]:
    page = max(query.page, 1)
    limit = min(max(query.limit, 1), 200)
    items, total = await repo.list_links(
        session,
        page=page,
        limit=limit,
        leasing_company_id=query.leasing_company_id,
        contractor_name=query.contractor_name,
        inn=query.inn,
    )
    pages = (total + limit - 1) // limit if total else 0
    return {
        "items": items,
        "pagination": {
            "page": page,
            "limit": limit,
            "total": total,
            "pages": pages,
        },
    }
