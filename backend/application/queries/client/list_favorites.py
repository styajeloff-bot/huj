"""Query: list the user's favorites with vehicle basic fields."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from domain.storefronts import DEFAULT_CATALOG_SCOPE, CatalogScope
from infrastructure.repositories import client_repository as repo


@dataclass(frozen=True)
class ListFavoritesQuery:
    user_id: UUID
    scope: CatalogScope = DEFAULT_CATALOG_SCOPE


async def handle_list_favorites(
    query: ListFavoritesQuery, session: AsyncSession
) -> list[dict[str, Any]]:
    return cast(
        "list[dict[str, Any]]",
        await repo.list_favorites(session, query.user_id, query.scope),
    )
