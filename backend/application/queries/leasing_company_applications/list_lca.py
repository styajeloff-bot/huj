"""List LeasingCompanyApplications (LCA) filtered by user role."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.permissions import require_distributor_application_read
from application.services.leasing_access import require_lc_context
from infrastructure.repositories import (
    application_documents_repository as application_documents_repo,
)
from infrastructure.repositories import (
    leasing_company_application_repository as lca_repo,
)
from infrastructure.repository_timing import timed_repository


@dataclass
class ListLcaQuery:
    actor_id: UUID
    actor_role: str
    actor_company_id: UUID | None = None
    actor_leasing_company_id: UUID | None = None
    status: str | None = None
    application_id: UUID | None = None
    page: int = 1
    limit: int = 20


@timed_repository
async def handle_list_lca(
    query: ListLcaQuery, session: AsyncSession
) -> dict[str, Any]:
    """Return LCA rows visible to the given user."""
    await require_distributor_application_read(
        session, user_id=query.actor_id, actor_role=query.actor_role,
        actor_company_id=query.actor_company_id,
    )
    lc_id = query.actor_leasing_company_id
    if query.actor_role == "leasing_company":
        context = await require_lc_context(
            session, user_id=query.actor_id, company_id=query.actor_company_id,
            leasing_company_id=lc_id,
        )
        lc_id = context["leasing_company_id"]
    result = cast("dict[str, Any]", await lca_repo.list_lca_rows_for_actor(
        session,
        actor_role=query.actor_role,
        actor_company_id=query.actor_company_id,
        actor_leasing_company_id=lc_id,
        status=query.status,
        application_id=query.application_id,
        page=query.page,
        limit=query.limit,
    ))
    # CheckoutOffersStep loads these LCA rows directly (rather than the parent
    # application projection), so preserve the same read-only document-process
    # status that the application detail endpoint exposes.
    if query.application_id is not None:
        display_statuses = await application_documents_repo.list_lc_display_statuses(
            session, application_id=query.application_id
        )
        for item in result["items"]:
            leasing_company_id = item.get("leasing_company_id")
            item["display_status"] = display_statuses.get(
                leasing_company_id, item.get("status")
            )
    return result
