"""Resolve the ``leasing_companies.id`` for the authenticated LC user.

The JWT claim carries ``company_id`` (companies-table id). LC actions need
the ``leasing_companies.id`` — this query translates one into the other,
falling back through ``leasing_company_users`` if present.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.repositories import (
    leasing_company_application_repository as lca_repo,
)


@dataclass
class ResolveActorLcQuery:
    user_id: UUID
    role: str


async def handle_resolve_actor_lc(
    query: ResolveActorLcQuery, session: AsyncSession
) -> UUID | None:
    if query.role != "leasing_company":
        return None
    return cast(
        "UUID | None",
        await lca_repo.resolve_lc_id_for_user(session, query.user_id),
    )
