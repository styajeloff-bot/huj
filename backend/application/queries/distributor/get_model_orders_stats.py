"""Counts of pending / assigned model orders."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.distributor_scope import resolve_distributor_scope
from infrastructure.repositories import distributor_repository as repo


@dataclass
class GetModelOrdersStatsQuery:
    actor_id: UUID
    actor_role: str


async def handle_get_model_orders_stats(
    query: GetModelOrdersStatsQuery, session: AsyncSession
) -> dict[str, Any]:
    scope = await resolve_distributor_scope(
        session,
        actor_id=query.actor_id, actor_role=query.actor_role
    )
    stats = await repo.count_model_orders_by_status(
        session, dealer_filter=scope.dealer_filter()
    )
    return {"stats": stats}
