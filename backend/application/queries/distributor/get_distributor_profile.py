"""Distributor profile — user + company + distributor extension."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.distributor_scope import resolve_distributor_scope
from domain.errors import UserNotFoundError
from infrastructure.repositories import distributor_repository as repo


@dataclass
class GetDistributorProfileQuery:
    actor_id: UUID
    actor_role: str


async def handle_get_distributor_profile(
    query: GetDistributorProfileQuery, session: AsyncSession
) -> dict[str, Any]:
    # The scope resolution doubles as a role guard: distributors and
    # employees are allowed, everyone else is rejected.
    await resolve_distributor_scope(session,
        actor_id=query.actor_id, actor_role=query.actor_role
    )
    profile = await repo.get_distributor_profile(session, query.actor_id)
    if profile is None:
        raise UserNotFoundError()
    return {"profile": profile}
