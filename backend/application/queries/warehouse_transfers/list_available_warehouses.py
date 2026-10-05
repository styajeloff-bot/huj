"""List warehouses accessible to a warehouse-transfer actor."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.distributor_scope import resolve_distributor_scope
from infrastructure.repositories import warehouse_repository as repository


@dataclass(frozen=True)
class ListAvailableWarehousesQuery:
    actor_id: UUID
    actor_role: str
    company_id: UUID | None = None


async def handle_list_available_warehouses(
    query: ListAvailableWarehousesQuery,
    session: AsyncSession,
) -> dict[str, Any]:
    scope = await resolve_distributor_scope(
        session,
        actor_id=query.actor_id,
        actor_role=query.actor_role,
        company_id=query.company_id,
    )
    warehouses = await repository.list_available_warehouses(
        session,
        dealer_filter=scope.dealer_filter(),
    )
    return {"warehouses": warehouses}
