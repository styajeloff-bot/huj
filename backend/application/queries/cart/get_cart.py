"""Query: list the user's cart with vehicle basic fields."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from domain.storefronts import DEFAULT_CATALOG_SCOPE, CatalogScope
from infrastructure.repositories import cart_repository as repo


@dataclass(frozen=True)
class GetCartQuery:
    user_id: UUID
    scope: CatalogScope = DEFAULT_CATALOG_SCOPE


async def handle_get_cart(
    query: GetCartQuery, session: AsyncSession
) -> list[dict[str, Any]]:
    return cast(
        "list[dict[str, Any]]",
        await repo.list_cart_items(session, query.user_id, query.scope),
    )
