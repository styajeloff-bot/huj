"""Add a vehicle to the user's favorites."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from domain.errors import FavoriteAlreadyExistsError, VehicleNotFoundError
from domain.storefronts import DEFAULT_CATALOG_SCOPE, CatalogScope
from infrastructure.repositories import client_repository as repo


@dataclass(frozen=True)
class AddFavoriteCommand:
    user_id: UUID
    vehicle_id: UUID
    scope: CatalogScope = DEFAULT_CATALOG_SCOPE


async def handle_add_favorite(
    cmd: AddFavoriteCommand, session: AsyncSession
) -> dict[str, Any]:
    if not await repo.vehicle_visible_for_favorites(
        session, cmd.vehicle_id, cmd.scope
    ):
        raise VehicleNotFoundError(cmd.vehicle_id)
    if await repo.is_favorite(
        session, cmd.user_id, cmd.vehicle_id, cmd.scope
    ):
        raise FavoriteAlreadyExistsError(cmd.vehicle_id)
    return cast(
        "dict[str, Any]",
        await repo.add_favorite(
            session, cmd.user_id, cmd.vehicle_id, cmd.scope
        ),
    )
