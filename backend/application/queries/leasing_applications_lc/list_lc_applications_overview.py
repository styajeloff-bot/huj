"""List leasing applications for LC cabinet with per-LC status."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.services.leasing_access import require_lc_context
from domain.errors import LeasingCompanyBindingNotConfiguredError
from infrastructure.repositories import (
    leasing_company_application_repository as lca_repo,
)


@dataclass
class ListLcApplicationsOverviewQuery:
    actor_user_id: UUID
    actor_role: str
    actor_leasing_company_id: UUID | None
    actor_company_id: UUID | None = None
    status: str | None = None
    page: int = 1
    limit: int = 20


async def handle_list_lc_applications_overview(
    query: ListLcApplicationsOverviewQuery, session: AsyncSession
) -> dict[str, Any]:
    if query.actor_role == "carcraft_employee":
        if query.actor_leasing_company_id is None:
            return _empty_result(query)
    elif query.actor_leasing_company_id is None:
        raise LeasingCompanyBindingNotConfiguredError()

    assert query.actor_leasing_company_id is not None
    if query.actor_role == "leasing_company":
        await require_lc_context(
            session, user_id=query.actor_user_id, company_id=query.actor_company_id,
            leasing_company_id=query.actor_leasing_company_id,
        )
    return cast("dict[str, Any]", await lca_repo.list_lc_applications_overview(
        session,
        leasing_company_id=query.actor_leasing_company_id,
        status=query.status,
        page=query.page,
        limit=query.limit,
    ))

def _empty_result(query: ListLcApplicationsOverviewQuery) -> dict[str, Any]:
    return {
        "applications": [],
        "pagination": {
            "page": query.page,
            "limit": query.limit,
            "total": 0,
            "pages": 0,
        },
    }
