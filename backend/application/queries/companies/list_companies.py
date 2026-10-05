"""Query: list all companies for the admin / directory UI.

carcraft_employee may browse the entire directory; other roles see only
the companies they are linked to (via ``users.company_id`` and
``user_companies``). For non-employees we filter against the full list of
linked ids.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.repositories import company_repository as repo


@dataclass(frozen=True)
class ListCompaniesQuery:
    actor_id: UUID
    actor_role: str | None
    page: int = 1
    limit: int = 20
    search: str | None = None
    name: str | None = None
    phone: str | None = None
    company_type: str | None = None
    is_active: bool | None = None
    include_relations: bool = False


async def handle_list_companies(
    query: ListCompaniesQuery, session: AsyncSession
) -> dict[str, Any]:
    if query.include_relations:
        items, total = await repo.list_companies_for_export(
            session,
            page=query.page,
            limit=query.limit,
            search=query.search,
            name=query.name,
            phone=query.phone,
            company_type=query.company_type,
            is_active=query.is_active,
        )
    else:
        items, total = await repo.list_companies(
            session,
            page=query.page,
            limit=query.limit,
            search=query.search,
            name=query.name,
            phone=query.phone,
            company_type=query.company_type,
            is_active=query.is_active,
        )

    if query.actor_role != "carcraft_employee":
        primary = await repo.get_user_company_id(session, query.actor_id)
        linked = set(await repo.list_user_company_ids(session, query.actor_id))
        if primary is not None:
            linked.add(primary)
        items = [item for item in items if item.get("id") in linked]
        total = len(items)

    pages = math.ceil(total / query.limit) if query.limit > 0 else 0
    return {
        "companies": items,
        "pagination": {
            "page": query.page,
            "limit": query.limit,
            "total": total,
            "pages": pages,
        },
    }
