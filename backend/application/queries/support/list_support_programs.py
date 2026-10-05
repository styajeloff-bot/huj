"""List support programs (admin)."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.distributor_scope import resolve_distributor_scope
from infrastructure.repositories import support_repository as repo


@dataclass
class ListSupportProgramsQuery:
    page: int = 1
    limit: int = 20
    search: str | None = None
    mark_id: str | None = None
    model_id: str | None = None
    dealer_group_id: UUID | None = None
    distributor_id: UUID | None = None
    is_active: bool | None = None
    actor_id: UUID | None = None
    actor_role: str = "carcraft_employee"
    company_id: UUID | None = None
    actor_company_id: UUID | None = None


async def handle_list_support_programs(
    query: ListSupportProgramsQuery, session: AsyncSession
) -> dict[str, Any]:
    scope = await resolve_distributor_scope(
        session,
        actor_id=query.actor_id or UUID(int=0),
        actor_role=query.actor_role,
        company_id=query.actor_company_id or query.company_id,
    )
    items, total = await repo.list_programs(
        session,
        page=query.page,
        limit=query.limit,
        search=query.search,
        mark_id=query.mark_id,
        model_id=query.model_id,
        dealer_group_id=query.dealer_group_id,
        distributor_id=query.distributor_id,
        is_active=query.is_active,
        visible_distributor_id=scope.company_id,
        restrict_to_distributor=not scope.is_employee,
    )
    pages = math.ceil(total / query.limit) if query.limit > 0 else 0
    return {
        "support_programs": items,
        "pagination": {
            "page": query.page,
            "limit": query.limit,
            "total": total,
            "pages": pages,
        },
    }
