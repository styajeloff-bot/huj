"""Get a single warehouse by id within the requesting actor's read scope."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.warehouse_scope import resolve_warehouse_dealer_filter
from domain.errors import WarehouseNotFoundError
from infrastructure.repositories import warehouse_repository as repo


@dataclass
class GetWarehouseQuery:
    warehouse_id: UUID
    actor_id: UUID | None = None
    actor_role: str = "carcraft_employee"
    company_id: UUID | None = None


async def handle_get_warehouse(
    query: GetWarehouseQuery, session: AsyncSession
) -> dict[str, Any]:
    dealer_filter = await resolve_warehouse_dealer_filter(
        session,
        actor_id=query.actor_id or UUID(int=0),
        actor_role=query.actor_role,
        company_id=query.company_id,
    )
    warehouse = await repo.get_by_id(
        session,
        query.warehouse_id,
        dealer_filter=dealer_filter,
        company_id=query.company_id,
        actor_role=query.actor_role,
    )
    if warehouse is None:
        raise WarehouseNotFoundError(query.warehouse_id)
    return cast("dict[str, Any]", warehouse)
