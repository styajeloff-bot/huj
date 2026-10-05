"""Query: number of cart items for the current user."""
from __future__ import annotations

from dataclasses import dataclass
from typing import cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from domain.storefronts import DEFAULT_CATALOG_SCOPE, CatalogScope
from infrastructure.repositories import cart_repository as repo


@dataclass(frozen=True)
class GetCartCountQuery:
    user_id: UUID
    scope: CatalogScope = DEFAULT_CATALOG_SCOPE


async def handle_get_cart_count(
    query: GetCartCountQuery, session: AsyncSession
) -> int:
    return cast(
        "int", await repo.count_cart_items(session, query.user_id, query.scope)
    )
