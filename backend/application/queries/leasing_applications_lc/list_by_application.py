"""List per-LC application links for a parent application.

The Phase 3 parent application aggregate exposes a list of
``leasing_company_applications`` entries (one per LC that was selected).
This query returns that list, enforcing the same read-ownership rules as
``GET /applications/{id}`` via the ``LeasingApplication`` aggregate.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.permissions import ensure_application_visible_to
from domain.errors import ApplicationNotFoundError
from infrastructure.repositories import application_repository as repo


@dataclass
class ListLcLinksByApplicationQuery:
    application_id: uuid.UUID
    actor_id: UUID
    actor_role: str
    actor_company_id: UUID | None
    actor_leasing_company_id: UUID | None = None


async def handle_list_lc_links_by_application(
    query: ListLcLinksByApplicationQuery, session: AsyncSession
) -> list[dict[str, Any]]:
    app_dict = await repo.get_by_id(session, query.application_id)
    if app_dict is None:
        raise ApplicationNotFoundError(query.application_id)
    await ensure_application_visible_to(
        session,
        application=app_dict,
        user_id=query.actor_id,
        actor_role=query.actor_role,
        actor_company_id=query.actor_company_id,
        actor_leasing_company_id=query.actor_leasing_company_id,
    )
    return cast(
        "list[dict[str, Any]]",
        await repo.list_lc_links(session, query.application_id),
    )
