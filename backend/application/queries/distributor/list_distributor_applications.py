"""List leasing applications visible to the distributor."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.distributor_scope import resolve_distributor_scope
from application.queries.applications.list_applications import (
    ListApplicationsQuery,
    handle_list_applications,
)
from infrastructure.repositories import distributor_repository as repo


@dataclass
class ListDistributorApplicationsQuery:
    actor_id: UUID
    actor_role: str
    company_id: UUID | None = None
    page: int = 1
    limit: int = 20
    status: str | None = None


async def handle_list_distributor_applications(
    query: ListDistributorApplicationsQuery, session: AsyncSession
) -> dict[str, Any]:
    if query.actor_role == "distributor":
        result = await handle_list_applications(ListApplicationsQuery(
            actor_id=query.actor_id, actor_role=query.actor_role,
            actor_company_id=query.company_id, page=query.page,
            limit=query.limit, status=query.status,
            kind="application",  # this feed is ordinary applications only
        ), session)
        return {"applications": result["applications"], "pagination": result["pagination"]}
    scope = await resolve_distributor_scope(
        session,
        actor_id=query.actor_id, actor_role=query.actor_role, company_id=query.company_id
    )
    items, total = await repo.list_distributor_applications(
        session,
        dealer_filter=scope.dealer_filter(),
        page=query.page,
        limit=query.limit,
        status=query.status,
    )
    pages = math.ceil(total / query.limit) if query.limit > 0 else 0
    return {
        "applications": items,
        "pagination": {
            "page": query.page,
            "limit": query.limit,
            "total": total,
            "pages": pages,
        },
    }
