"""List applications the current LC can review."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.services.leasing_access import require_lc_context
from domain.application_sources import source_filter_values
from domain.errors import LeasingCompanyBindingNotConfiguredError
from infrastructure.repositories import (
    leasing_company_application_repository as lca_repo,
)


@dataclass
class ListLcApplicationsQuery:
    actor_user_id: UUID
    actor_role: str
    actor_leasing_company_id: UUID | None
    actor_company_id: UUID | None = None
    status: str | None = None
    source_type: str | None = None
    search: str | None = None
    page: int = 1
    limit: int = 20


async def handle_list_lc_applications(
    query: ListLcApplicationsQuery, session: AsyncSession
) -> dict[str, Any]:
    if query.actor_leasing_company_id is None:
        # Employees / other actors without an LC binding get empty by
        # design — the endpoint is scoped to LC cabinet use.
        if query.actor_role == "carcraft_employee":
            return {
                "applications": [],
                "pagination": {
                    "page": query.page,
                    "limit": query.limit,
                    "total": 0,
                    "pages": 0,
                },
            }
        raise LeasingCompanyBindingNotConfiguredError()

    if query.actor_role == "leasing_company":
        await require_lc_context(
            session, user_id=query.actor_user_id, company_id=query.actor_company_id,
            leasing_company_id=query.actor_leasing_company_id,
        )
    offset = max(query.page - 1, 0) * max(query.limit, 1)
    source_types = source_filter_values(query.source_type)
    rows = await lca_repo.list_applications_for_lc(
        session,
        leasing_company_id=query.actor_leasing_company_id,
        status=query.status,
        source_types=source_types,
        search=query.search,
        limit=query.limit,
        offset=offset,
    )
    total = await lca_repo.count_applications_for_lc(
        session,
        leasing_company_id=query.actor_leasing_company_id,
        status=query.status,
        source_types=source_types,
        search=query.search,
    )
    pages = (total + query.limit - 1) // query.limit if query.limit else 0
    return {
        "applications": rows,
        "pagination": {
            "page": query.page,
            "limit": query.limit,
            "total": total,
            "pages": pages,
        },
    }
