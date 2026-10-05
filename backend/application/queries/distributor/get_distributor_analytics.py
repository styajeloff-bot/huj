"""Distributor analytics — breakdown by status / mark + monthly timeline."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.distributor_scope import resolve_distributor_scope
from infrastructure.repositories import distributor_repository as repo


@dataclass
class GetDistributorAnalyticsQuery:
    actor_id: UUID
    actor_role: str
    company_id: UUID | None = None


async def handle_get_distributor_analytics(
    query: GetDistributorAnalyticsQuery, session: AsyncSession
) -> dict[str, Any]:
    scope = await resolve_distributor_scope(
        session,
        actor_id=query.actor_id, actor_role=query.actor_role, company_id=query.company_id
    )
    analytics = await repo.get_distributor_analytics(
        session, dealer_filter=scope.dealer_filter()
    )
    return {"analytics": analytics}
