"""Bulk-remove multiple vehicles from the user's favorites."""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from domain.storefronts import DEFAULT_CATALOG_SCOPE, CatalogScope
from infrastructure.repositories import client_repository as repo


@dataclass(frozen=True)
class BulkRemoveFavoritesCommand:
    user_id: UUID
    vehicle_ids: Sequence[UUID] = field(default_factory=tuple)
    scope: CatalogScope = DEFAULT_CATALOG_SCOPE


async def handle_bulk_remove_favorites(
    cmd: BulkRemoveFavoritesCommand, session: AsyncSession
) -> int:
    return cast(
        "int",
        await repo.bulk_remove_favorites(
            session, cmd.user_id, list(cmd.vehicle_ids), cmd.scope
        ),
    )
