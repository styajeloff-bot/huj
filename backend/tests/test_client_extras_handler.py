"""Handler-level tests for the G4 client additions.

Scope reduced in Phase 11 R8: the ``/client/2fa/*`` preference toggle
was removed — MFA is now managed exclusively through ``/auth/mfa``.
The remaining coverage here is the clear-favorites helper.
"""
from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from application.commands.client import (
    AddFavoriteCommand,
    ClearFavoritesCommand,
    handle_add_favorite,
    handle_clear_favorites,
)
from infrastructure.models.users import User
from tests.legacy_compat import Vehicle

pytestmark = pytest.mark.asyncio


async def test_clear_favorites_wipes_everything(
    db_session: AsyncSession, client_user: User
) -> None:
    v1 = Vehicle(status="available", is_available=True)
    v2 = Vehicle(status="available", is_available=True)
    db_session.add_all([v1, v2])
    await db_session.flush()

    await handle_add_favorite(
        AddFavoriteCommand(user_id=client_user.id, vehicle_id=v1.id), db_session
    )
    await handle_add_favorite(
        AddFavoriteCommand(user_id=client_user.id, vehicle_id=v2.id), db_session
    )

    removed = await handle_clear_favorites(
        ClearFavoritesCommand(user_id=client_user.id), db_session
    )
    assert removed == 2

    # Idempotent
    removed_again = await handle_clear_favorites(
        ClearFavoritesCommand(user_id=client_user.id), db_session
    )
    assert removed_again == 0
