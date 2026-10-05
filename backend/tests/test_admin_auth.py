"""Integration tests for /api/v1/admin/auth/* endpoints.

Covers:
 * Employee with `auth:admin` scope can list / force-logout / disable
   any user's sessions.
 * Client without `auth:admin` gets 403 INSUFFICIENT_PERMISSIONS.
 * Disabling propagates to `users.is_active = False` + wipes sessions.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.auth import hash_refresh_token
from infrastructure.models.users import User, UserSession
from infrastructure.repositories import auth_repository as auth_repo
from infrastructure.settings import settings

pytestmark = pytest.mark.asyncio


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _seed_session(db: AsyncSession, user_id: UUID) -> UUID:
    expires = datetime.now(UTC) + timedelta(days=settings.refresh_token_expiry_days)
    row = await auth_repo.create_user_session(
        db,
        user_id=user_id,
        refresh_token_hash=hash_refresh_token("seed"),
        expires_at=expires,
        ip_address="8.8.8.8",
        user_agent="pytest-admin",
    )
    return cast("UUID", row["id"])


# ---------------------------------------------------------------------------
# GET /users/{id}/sessions (admin-scope)
# ---------------------------------------------------------------------------


async def test_admin_list_sessions_employee_sees_any_user(
    client: AsyncClient,
    db_session: AsyncSession,
    client_user: User,
    employee_token: str,
) -> None:
    sid = await _seed_session(db_session, client_user.id)

    resp = await client.get(
        f"/api/v1/users/{client_user.id}/sessions",
        headers=_auth(employee_token),
    )
    assert resp.status_code == 200
    ids = [UUID(s["id"]) for s in resp.json()["sessions"]]
    assert sid in ids


async def test_admin_list_sessions_client_forbidden(
    client: AsyncClient,
    db_session: AsyncSession,
    other_user: User,
    client_token: str,
) -> None:
    await _seed_session(db_session, other_user.id)

    resp = await client.get(
        f"/api/v1/users/{other_user.id}/sessions",
        headers=_auth(client_token),
    )
    assert resp.status_code == 403
    assert resp.json()["code"] == "INSUFFICIENT_PERMISSIONS"


async def test_admin_list_sessions_unauthenticated(
    client: AsyncClient,
    client_user: User,
) -> None:
    resp = await client.get(
        f"/api/v1/users/{client_user.id}/sessions"
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# DELETE /users/{id}/sessions — admin force-logout (R1 replacement)
# ---------------------------------------------------------------------------


async def test_admin_force_logout_wipes_sessions(
    client: AsyncClient,
    db_session: AsyncSession,
    client_user: User,
    employee_token: str,
) -> None:
    await _seed_session(db_session, client_user.id)
    await _seed_session(db_session, client_user.id)

    resp = await client.delete(
        f"/api/v1/users/{client_user.id}/sessions",
        headers=_auth(employee_token),
    )
    assert resp.status_code == 200
    assert resp.json()["revokedCount"] == 2

    remaining = (
        await db_session.execute(
            select(UserSession).where(UserSession.user_id == client_user.id)
        )
    ).scalars().all()
    assert remaining == []


async def test_admin_force_logout_client_forbidden(
    client: AsyncClient,
    client_user: User,
    other_user: User,
    client_token: str,
) -> None:
    resp = await client.delete(
        f"/api/v1/users/{other_user.id}/sessions",
        headers=_auth(client_token),
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# PATCH /users/{id} — status toggle (R1 replacement for disable/enable)
# ---------------------------------------------------------------------------


async def test_admin_disable_flips_flag_and_wipes_sessions(
    client: AsyncClient,
    db_session: AsyncSession,
    client_user: User,
    employee_token: str,
) -> None:
    await _seed_session(db_session, client_user.id)

    resp = await client.patch(
        f"/api/v1/users/{client_user.id}",
        headers=_auth(employee_token),
        json={"status": "disabled"},
    )
    assert resp.status_code == 200

    refreshed = await db_session.get(User, client_user.id)
    assert refreshed is not None
    assert refreshed.is_active is False

    sessions = (
        await db_session.execute(
            select(UserSession).where(UserSession.user_id == client_user.id)
        )
    ).scalars().all()
    assert sessions == []


async def test_admin_enable_sets_is_active_true(
    client: AsyncClient,
    db_session: AsyncSession,
    client_user: User,
    employee_token: str,
) -> None:
    # Flip off first
    client_user.is_active = False  # type: ignore[assignment]
    await db_session.flush()

    resp = await client.patch(
        f"/api/v1/users/{client_user.id}",
        headers=_auth(employee_token),
        json={"status": "active"},
    )
    assert resp.status_code == 200

    refreshed = await db_session.get(User, client_user.id)
    assert refreshed is not None
    assert refreshed.is_active is True


async def test_admin_disable_client_forbidden(
    client: AsyncClient,
    client_user: User,
    other_user: User,
    client_token: str,
) -> None:
    resp = await client.patch(
        f"/api/v1/users/{other_user.id}",
        headers=_auth(client_token),
        json={"status": "disabled"},
    )
    assert resp.status_code == 403


async def test_admin_patch_status_rejects_me(
    client: AsyncClient,
    employee_token: str,
    employee_user: User,
) -> None:
    """Admin cannot disable themselves via `me`.

    After Phase 13 R13a consolidated the role-specific profile endpoints
    into ``/users/me``, that route is now a dedicated profile-edit
    surface with ``extra="forbid"`` on the body. The ``status`` field
    lives exclusively on the admin-scoped ``PATCH /users/{id}`` — calls
    to ``/users/me`` with a ``status`` field therefore fail at
    validation (422), still preventing self-disable.
    """
    resp = await client.patch(
        "/api/v1/users/me",
        headers=_auth(employee_token),
        json={"status": "disabled"},
    )
    assert resp.status_code == 422


async def test_admin_patch_status_rejects_self_id(
    client: AsyncClient,
    employee_token: str,
    employee_user: User,
) -> None:
    """Admin cannot disable themselves via their own numeric id either."""
    resp = await client.patch(
        f"/api/v1/users/{employee_user.id}",
        headers=_auth(employee_token),
        json={"status": "disabled"},
    )
    assert resp.status_code == 403
