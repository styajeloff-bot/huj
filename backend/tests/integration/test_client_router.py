"""Integration tests for /api/v1/client/* (full HTTP round-trip)."""
from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.models.users import User, UserFavorite
from tests.legacy_compat import Vehicle

pytestmark = pytest.mark.asyncio


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _seed_vehicle(db: AsyncSession) -> Vehicle:
    v = Vehicle(status="available", is_available=True)
    db.add(v)
    await db.flush()
    await db.refresh(v)
    return v


# ---------------------------------------------------------------------------
# /profile endpoints were consolidated into /users/me in Phase 13 R13a.
# Tests for the unified surface live in tests/integration/test_users_me_router.py.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Phase 15 H3 — /client/profile/{send-sms,phone-change/verify} and
# /client/saved-calculations{,/:id} were deleted. Phone-change lives at
# /users/me/phone-change{,/verify} (covered in test_users_me_router.py /
# test_client_g4_router.py); saved calculations are served via the
# canonical /client/calculations alias (covered below).
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Favorites
# ---------------------------------------------------------------------------


async def test_list_favorites_empty(
    client: AsyncClient, client_token: str
) -> None:
    response = await client.get(
        "/api/v1/client/favorites", headers=_auth(client_token)
    )
    assert response.status_code == 200
    assert response.json() == {"favorites": []}


async def test_add_favorite_then_check_then_list(
    client: AsyncClient,
    client_token: str,
    db_session: AsyncSession,
) -> None:
    vehicle = await _seed_vehicle(db_session)
    add = await client.post(
        f"/api/v1/client/favorites/{vehicle.id}",
        headers=_auth(client_token),
    )
    assert add.status_code == 201, add.text
    body = add.json()
    assert body["vehicle_id"] == str(vehicle.id)

    listed = await client.get(
        "/api/v1/client/favorites", headers=_auth(client_token)
    )
    assert listed.status_code == 200
    favs = listed.json()["favorites"]
    assert len(favs) == 1
    assert favs[0]["vehicle_id"] == str(vehicle.id)


async def test_add_favorite_duplicate_409(
    client: AsyncClient,
    client_token: str,
    db_session: AsyncSession,
) -> None:
    vehicle = await _seed_vehicle(db_session)
    await client.post(
        f"/api/v1/client/favorites/{vehicle.id}",
        headers=_auth(client_token),
    )
    again = await client.post(
        f"/api/v1/client/favorites/{vehicle.id}",
        headers=_auth(client_token),
    )
    assert again.status_code == 409


async def test_remove_favorite_idempotent_204(
    client: AsyncClient,
    client_token: str,
    db_session: AsyncSession,
) -> None:
    vehicle = await _seed_vehicle(db_session)
    response = await client.delete(
        f"/api/v1/client/favorites/{vehicle.id}",
        headers=_auth(client_token),
    )
    assert response.status_code == 204


async def test_remove_favorite_actual_204(
    client: AsyncClient,
    client_token: str,
    client_user: User,
    db_session: AsyncSession,
) -> None:
    vehicle = await _seed_vehicle(db_session)
    db_session.add(
        UserFavorite(user_id=client_user.id, vehicle_id=vehicle.id)
    )
    await db_session.flush()

    response = await client.delete(
        f"/api/v1/client/favorites/{vehicle.id}",
        headers=_auth(client_token),
    )
    assert response.status_code == 204


async def test_bulk_remove_favorites_only_users_own(
    client: AsyncClient,
    client_token: str,
    client_user: User,
    other_user: User,
    db_session: AsyncSession,
) -> None:
    v1 = await _seed_vehicle(db_session)
    v2 = await _seed_vehicle(db_session)
    db_session.add(UserFavorite(user_id=client_user.id, vehicle_id=v1.id))
    db_session.add(UserFavorite(user_id=client_user.id, vehicle_id=v2.id))
    db_session.add(UserFavorite(user_id=other_user.id, vehicle_id=v1.id))
    await db_session.flush()

    response = await client.delete(
        f"/api/v1/client/favorites?ids={v1.id}&ids={v2.id}",
        headers=_auth(client_token),
    )
    assert response.status_code == 200, response.text
    assert response.json() == {"removed": 2}


async def test_delete_favorites_clear_all_requires_confirm(
    client: AsyncClient,
    client_token: str,
    client_user: User,
    db_session: AsyncSession,
) -> None:
    v = await _seed_vehicle(db_session)
    db_session.add(UserFavorite(user_id=client_user.id, vehicle_id=v.id))
    await db_session.flush()

    response = await client.delete(
        "/api/v1/client/favorites",
        headers=_auth(client_token),
    )
    assert response.status_code == 422

    confirmed = await client.delete(
        "/api/v1/client/favorites?confirm=true",
        headers=_auth(client_token),
    )
    assert confirmed.status_code == 200
    assert confirmed.json() == {"removed": 1}


async def test_favorites_no_auth_401(client: AsyncClient) -> None:
    response = await client.get("/api/v1/client/favorites")
    assert response.status_code == 401
