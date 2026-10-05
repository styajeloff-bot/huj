"""Remove a vehicle from the user's favorites (idempotent)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from domain.storefronts import DEFAULT_CATALOG_SCOPE, CatalogScope
from infrastructure.repositories import client_repository as repo


@dataclass(frozen=True)
class RemoveFavoriteCommand:
    user_id: UUID
    vehicle_id: UUID
    scope: CatalogScope = DEFAULT_CATALOG_SCOPE


async def handle_remove_favorite(
    cmd: RemoveFavoriteCommand, session: AsyncSession
) -> bool:
    """Returns True if a row was actually removed; False on idempotent no-op."""
    return cast(
        "bool",
        await repo.remove_favorite(
            session, cmd.user_id, cmd.vehicle_id, cmd.scope
        ),
    )
