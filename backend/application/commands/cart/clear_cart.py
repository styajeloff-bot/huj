"""Clear all cart items for the current user."""
from __future__ import annotations

from dataclasses import dataclass
from typing import cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from domain.storefronts import DEFAULT_CATALOG_SCOPE, CatalogScope
from infrastructure.repositories import cart_repository as repo


@dataclass(frozen=True)
class ClearCartCommand:
    user_id: UUID
    scope: CatalogScope = DEFAULT_CATALOG_SCOPE


async def handle_clear_cart(
    cmd: ClearCartCommand, session: AsyncSession
) -> int:
    """Return the number of removed rows."""
    return cast("int", await repo.clear_cart(session, cmd.user_id, cmd.scope))
