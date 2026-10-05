"""Support programs visible to the distributor."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.distributor_scope import resolve_distributor_scope
from infrastructure.repositories import support_repository as repo


@dataclass
class ListDistributorSupportProgramsQuery:
    actor_id: UUID
    actor_role: str
    actor_company_id: UUID | None = None
    page: int = 1
    limit: int = 20


async def handle_list_distributor_support_programs(
    query: ListDistributorSupportProgramsQuery, session: AsyncSession
) -> dict[str, Any]:
    scope = await resolve_distributor_scope(
        session,
        actor_id=query.actor_id,
        actor_role=query.actor_role,
        company_id=query.actor_company_id,
    )
    if not scope.is_employee and scope.company_id is None:
        return _empty_result(query)
    items, total = await repo.list_programs(
        session,
        visible_distributor_id=None if scope.is_employee else scope.company_id,
        restrict_to_distributor=not scope.is_employee,
        page=query.page,
        limit=query.limit,
    )
    pages = math.ceil(total / query.limit) if query.limit > 0 else 0
    return {
        "items": items,
        "pagination": {
            "page": query.page,
            "limit": query.limit,
            "total": total,
            "pages": pages,
        },
    }


def _empty_result(query: ListDistributorSupportProgramsQuery) -> dict[str, Any]:
    return {
        "items": [],
        "pagination": {
            "page": query.page,
            "limit": query.limit,
            "total": 0,
            "pages": 0,
        },
    }
