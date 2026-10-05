"""Clear all favorites of the current user."""
from __future__ import annotations

from dataclasses import dataclass
from typing import cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from domain.storefronts import DEFAULT_CATALOG_SCOPE, CatalogScope
from infrastructure.repositories import client_repository as repo


@dataclass(frozen=True)
class ClearFavoritesCommand:
    user_id: UUID
    scope: CatalogScope = DEFAULT_CATALOG_SCOPE


async def handle_clear_favorites(
    cmd: ClearFavoritesCommand, session: AsyncSession
) -> int:
    return cast(
        "int", await repo.clear_favorites(session, cmd.user_id, cmd.scope)
    )
