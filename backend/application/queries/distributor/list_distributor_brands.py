"""Distinct brand names in the distributor's scope.

Powers the inventory UI's brand dropdown, which expects ``{brands: [...]}``
with plain strings.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.distributor_scope import resolve_distributor_scope
from infrastructure.repositories import distributor_repository as repo


@dataclass
@dataclass
class ListDistributorBrandsQuery:
    actor_id: UUID
    actor_role: str
    company_id: UUID | None = None


async def handle_list_distributor_brands(
    query: ListDistributorBrandsQuery, session: AsyncSession
) -> dict[str, Any]:
    scope = await resolve_distributor_scope(
        session,
        actor_id=query.actor_id, actor_role=query.actor_role,
        company_id=query.company_id
    )
    brands = await repo.list_distributor_brand_names(
        session, dealer_filter=scope.dealer_filter()
    )
    return {"brands": brands}
