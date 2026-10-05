"""Get a single LeasingCompanyApplication by ID with ownership check."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.permissions import ensure_application_visible_to
from application.services.leasing_access import require_lc_context
from domain.errors import (
    ApplicationNotFoundError,
    ApplicationNotOwnedError,
    LeasingCompanyApplicationNotFoundError,
)
from infrastructure.repositories import application_repository as app_repo
from infrastructure.repositories import (
    leasing_company_application_repository as lca_repo,
)
from infrastructure.repository_timing import timed_repository


@dataclass
class GetLcaQuery:
    lca_id: UUID
    actor_id: UUID
    actor_role: str
    actor_company_id: UUID | None = None
    actor_leasing_company_id: UUID | None = None


@timed_repository
async def handle_get_lca(
    query: GetLcaQuery, session: AsyncSession
) -> dict[str, Any]:
    """Return LCA detail if the actor owns the parent application."""
    row = await lca_repo.get_link_by_id(session, query.lca_id)
    if row is None:
        raise LeasingCompanyApplicationNotFoundError(f"LCA {query.lca_id} not found")
    if query.actor_role == "leasing_company":
        context = await require_lc_context(
            session, user_id=query.actor_id, company_id=query.actor_company_id,
            leasing_company_id=query.actor_leasing_company_id,
        )
        if context["leasing_company_id"] != row["leasing_company_id"]:
            raise ApplicationNotOwnedError()

    app_dict = await app_repo.get_by_id(session, row["application_id"])
    if app_dict is None:
        raise ApplicationNotFoundError(row["application_id"])

    await ensure_application_visible_to(
        session,
        application=app_dict,
        user_id=query.actor_id,
        actor_role=query.actor_role,
        actor_company_id=query.actor_company_id,
        actor_leasing_company_id=query.actor_leasing_company_id,
    )

    return cast("dict[str, Any]", row)
