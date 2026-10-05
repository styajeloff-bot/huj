"""List distinct warehouse brands within the requesting actor's read scope."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.warehouse_scope import resolve_warehouse_dealer_filter
from infrastructure.repositories import warehouse_repository as repo


@dataclass
class ListWarehouseBrandsQuery:
    actor_id: UUID | None = None
    actor_role: str = "carcraft_employee"
    company_id: UUID | None = None


async def handle_list_warehouse_brands(
    query: ListWarehouseBrandsQuery,
    session: AsyncSession,
) -> dict[str, Any]:
    dealer_filter = await resolve_warehouse_dealer_filter(
        session,
        actor_id=query.actor_id or UUID(int=0),
        actor_role=query.actor_role,
        company_id=query.company_id,
    )
    brands = await repo.list_warehouse_brands(
        session, dealer_filter=dealer_filter
    )
    # Drop empty strings / Nones that distinct may surface.
    cleaned = [b for b in brands if b]
    return {"brands": cleaned}
