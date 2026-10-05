"""Atomic ``is_selected`` toggle across many cart positions."""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from domain.storefronts import DEFAULT_CATALOG_SCOPE, CatalogScope
from infrastructure.repositories import cart_repository as repo


@dataclass(frozen=True)
class BulkUpdateCartSelectionCommand:
    user_id: UUID
    items: Sequence[tuple[UUID, bool]]  # (vehicle_id, is_selected)
    scope: CatalogScope = DEFAULT_CATALOG_SCOPE


async def handle_bulk_update_cart_selection(
    cmd: BulkUpdateCartSelectionCommand, session: AsyncSession
) -> list[dict[str, Any]]:
    return cast(
        "list[dict[str, Any]]",
        await repo.bulk_update_selection(
            session, cmd.user_id, cmd.items, cmd.scope
        ),
    )


__all__ = [
    "BulkUpdateCartSelectionCommand",
    "handle_bulk_update_cart_selection",
]
