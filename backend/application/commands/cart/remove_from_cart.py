"""Idempotently remove a vehicle from the user's cart."""
from __future__ import annotations

from dataclasses import dataclass
from typing import cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from domain.storefronts import DEFAULT_CATALOG_SCOPE, CatalogScope
from infrastructure.repositories import cart_repository as repo


@dataclass(frozen=True)
class RemoveFromCartCommand:
    user_id: UUID
    vehicle_id: UUID
    scope: CatalogScope = DEFAULT_CATALOG_SCOPE


async def handle_remove_from_cart(
    cmd: RemoveFromCartCommand, session: AsyncSession
) -> bool:
    """Delete the ``(user_id, vehicle_id)`` row if it exists.

    Returns True when a row was removed, False when nothing was there.
    Mirrors Express idempotent behavior — the router maps both outcomes
    to an HTTP 200 response and never raises 404 here.
    """
    return cast(
        "bool",
        await repo.remove_item(
            session, cmd.user_id, cmd.vehicle_id, cmd.scope
        ),
    )
