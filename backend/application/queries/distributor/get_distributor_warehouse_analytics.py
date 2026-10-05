"""Distributor warehouse analytics — rich breakdown by status / mark / dealer / city."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.distributor_scope import resolve_distributor_scope
from infrastructure.repositories import distributor_repository as repo


@dataclass
class GetDistributorWarehouseAnalyticsQuery:
    actor_id: UUID
    actor_role: str


async def handle_get_distributor_warehouse_analytics(
    query: GetDistributorWarehouseAnalyticsQuery, session: AsyncSession
) -> dict[str, Any]:
    scope = await resolve_distributor_scope(
        session,
        actor_id=query.actor_id, actor_role=query.actor_role
    )
    analytics = await repo.get_distributor_warehouse_analytics(
        session, dealer_filter=scope.dealer_filter()
    )
    return {"analytics": analytics}
