"""Applications grouped by status for the distributor cabinet."""
from __future__ import annotations

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
class ListDistributorApplicationsGroupedQuery:
    actor_id: UUID
    actor_role: str
    company_id: UUID | None = None
    page: int = 1
    limit: int = 500


async def handle_list_distributor_applications_grouped(
    query: ListDistributorApplicationsGroupedQuery, session: AsyncSession
) -> dict[str, Any]:
    if query.actor_role == "distributor":
        result = await handle_list_applications(ListApplicationsQuery(
            actor_id=query.actor_id, actor_role=query.actor_role,
            actor_company_id=query.company_id, page=query.page, limit=query.limit,
        ), session)
        grouped_result: dict[str, list[dict[str, Any]]] = {}
        for application in result["applications"]:
            grouped_result.setdefault(str(application.get("status") or "unknown"), []).append(application)
        return {"applications": grouped_result, "pagination": result["pagination"]}
    scope = await resolve_distributor_scope(
        session,
        actor_id=query.actor_id, actor_role=query.actor_role, company_id=query.company_id
    )
    grouped, total = await repo.list_distributor_applications_grouped(
        session,
        dealer_filter=scope.dealer_filter(),
        page=query.page,
        limit=query.limit,
    )
    pages = (total + query.limit - 1) // query.limit if query.limit else 0
    return {
        "applications": grouped,
        "pagination": {
            "page": query.page,
            "limit": query.limit,
            "total": total,
            "pages": pages,
        },
    }
