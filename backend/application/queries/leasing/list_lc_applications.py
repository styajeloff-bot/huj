"""List applications the current LC can review."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.queries.fast_deals.merged import (
    lc_entry_key,
    merged_page,
    resolve_list_actor,
)
from application.services.leasing_access import require_lc_context
from domain.application_sources import source_filter_values
from domain.errors import LeasingCompanyBindingNotConfiguredError
from domain.fast_deals.values import Role
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
    # ``application`` / ``fast_deal``: which kind of rows the shared list returns.
    kind: str | None = None


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
    leasing_company_id: UUID = query.actor_leasing_company_id
    source_types = source_filter_values(query.source_type)

    async def fetch_ordinary(page: int, limit: int) -> tuple[list[dict[str, Any]], int]:
        rows = await lca_repo.list_applications_for_lc(
            session,
            leasing_company_id=leasing_company_id,
            status=query.status,
            source_types=source_types,
            search=query.search,
            limit=limit,
            offset=max(page - 1, 0) * max(limit, 1),
        )
        count = await lca_repo.count_applications_for_lc(
            session,
            leasing_company_id=leasing_company_id,
            status=query.status,
            source_types=source_types,
            search=query.search,
        )
        return rows, count

    # Only the leasing company's own cabinet gets fast deals: an employee who looks
    # at a company's queue through its binding must not see every platform deal.
    fast_actor = (
        await resolve_list_actor(
            session,
            user_id=query.actor_user_id,
            role=query.actor_role,
            company_id=query.actor_company_id,
        )
        if query.actor_role == Role.LEASING_COMPANY
        else None
    )
    rows, total = await merged_page(
        session,
        actor=fast_actor,
        kind=query.kind,
        ordinary_filtered=bool(query.status) or bool(source_types),
        search=query.search,
        page=query.page,
        limit=query.limit,
        fetch_ordinary=fetch_ordinary,
        ordinary_key=lc_entry_key,
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
