"""Integration tests for the G4 client additions."""
from __future__ import annotations

from uuid import UUID

import pytest
import pytest_asyncio
import sqlalchemy as sa
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.models.users import User, UserFavorite, VerificationCode
from tests.legacy_compat import Vehicle

pytestmark = pytest.mark.asyncio


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def seed_favorites(
    db_session: AsyncSession, client_user: User
) -> list[UUID]:
    ids: list[UUID] = []
    for _ in range(3):
        v = Vehicle(status="available", is_available=True)
        db_session.add(v)
        await db_session.flush()
        await db_session.refresh(v)
        db_session.add(UserFavorite(user_id=client_user.id, vehicle_id=v.id))
        ids.append(v.id)
    await db_session.flush()
    return ids


# ---------------------------------------------------------------------------
# DELETE /favorites?ids=... (bulk-remove) — collection DELETE with query
# ---------------------------------------------------------------------------


async def test_delete_favorites_by_ids(
    client: AsyncClient,
    client_token: str,
    db_session: AsyncSession,
    seed_favorites: list[int],
) -> None:
    query = "&".join(f"ids={vid}" for vid in seed_favorites[:2])
    response = await client.delete(
        f"/api/v1/client/favorites?{query}",
        headers=_auth(client_token),
    )
    assert response.status_code == 200, response.text
    assert response.json()["removed"] == 2


async def test_delete_favorites_by_ids_requires_auth(client: AsyncClient) -> None:
    response = await client.delete("/api/v1/client/favorites?ids=1&ids=2")
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# DELETE /favorites?confirm=true — clear-all
# ---------------------------------------------------------------------------


async def test_clear_favorites_removes_all(
    client: AsyncClient,
    client_token: str,
    db_session: AsyncSession,
    client_user: User,
    seed_favorites: list[int],
) -> None:
    response = await client.delete(
        "/api/v1/client/favorites?confirm=true",
        headers=_auth(client_token),
    )
    assert response.status_code == 200, response.text
    assert response.json()["removed"] == len(seed_favorites)
    remaining = (
        await db_session.execute(
            sa.select(sa.func.count(UserFavorite.id)).where(
                UserFavorite.user_id == client_user.id
            )
        )
    ).scalar_one()
    assert remaining == 0


async def test_clear_favorites_idempotent(
    client: AsyncClient, client_token: str
) -> None:
    response = await client.delete(
        "/api/v1/client/favorites?confirm=true",
        headers=_auth(client_token),
    )
    assert response.status_code == 200
    assert response.json()["removed"] == 0


async def test_clear_favorites_without_confirm_returns_422(
    client: AsyncClient,
    client_token: str,
    seed_favorites: list[int],
) -> None:
    response = await client.delete(
        "/api/v1/client/favorites", headers=_auth(client_token)
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# phone-change POST aliases
# ---------------------------------------------------------------------------


async def test_phone_change_request_post_writes_code(
    client: AsyncClient,
    client_token: str,
    db_session: AsyncSession,
) -> None:
    new_phone = "+76660004599"
    response = await client.post(
        "/api/v1/users/me/phone-change",
        headers=_auth(client_token),
        json={"new_phone": new_phone},
    )
    assert response.status_code == 200, response.text
    rows = (
        await db_session.execute(
            sa.select(VerificationCode).where(
                VerificationCode.phone == new_phone
            )
        )
    ).scalars().all()
    assert len(rows) == 1


async def test_phone_change_verify_post_alias_rejects_bad_code(
    client: AsyncClient, client_token: str
) -> None:
    response = await client.post(
        "/api/v1/users/me/phone-change/verify",
        headers=_auth(client_token),
        json={"new_phone": "+76660004500", "code": "9999"},
    )
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# /2fa/{action} — removed in Phase 11 R8. MFA lifecycle lives under
# /auth/mfa now; see tests/test_mfa.py + tests/test_mfa_enforcement.py.
# ---------------------------------------------------------------------------


async def test_client_2fa_legacy_endpoint_gone(
    client: AsyncClient, client_token: str
) -> None:
    response = await client.post(
        "/api/v1/client/2fa/enable", headers=_auth(client_token)
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# /calculations aliases
# ---------------------------------------------------------------------------


async def test_calculations_full_roundtrip(
    client: AsyncClient, client_token: str
) -> None:
    created = await client.post(
        "/api/v1/client/calculations",
        headers=_auth(client_token),
        json={
            "name": "Saved",
            "params": {"a": 1},
            "calculation": {"b": 2},
        },
    )
    assert created.status_code == 201, created.text
    calc_id = created.json()["id"]

    listing = await client.get(
        "/api/v1/client/calculations", headers=_auth(client_token)
    )
    assert listing.status_code == 200
    ids = [item["id"] for item in listing.json()["calculations"]]
    assert calc_id in ids

    deleted = await client.delete(
        f"/api/v1/client/calculations/{calc_id}",
        headers=_auth(client_token),
    )
    assert deleted.status_code == 204
