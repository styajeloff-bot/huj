"""Integration tests for BE-1: inactive-session timeout on refresh + listing.

The refresh path (``POST /auth/refresh``) must reject a session whose
``last_used_at`` is older than the role-specific cap, even if the absolute
``expires_at`` hasn't been reached. The caller-visible session list
(``GET /auth/sessions``) must filter those same rows out so the UI never
advertises a device the server won't honour.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.auth import generate_tokens, hash_refresh_token
from infrastructure.models.users import User, UserSession
from infrastructure.repositories import auth_repository as auth_repo
from infrastructure.settings import settings

pytestmark = pytest.mark.asyncio


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _seed_session(
    db: AsyncSession,
    user_id: UUID,
    role: str,
    *,
    last_used_delta: timedelta,
) -> tuple[UUID, str]:
    """Create a session, then back-date ``last_used_at`` by ``last_used_delta``.

    Returns (session_id, refresh_jwt). The refresh hash is kept in sync so
    the server accepts the JWT on replay (i.e. no reuse-detection false
    positive).
    """
    expires = datetime.now(UTC) + timedelta(days=settings.refresh_token_expiry_days)
    row = await auth_repo.create_user_session(
        db,
        user_id=user_id,
        refresh_token_hash=hash_refresh_token("seed"),
        expires_at=expires,
    )
    _, refresh = generate_tokens(user_id, role, None, refresh_session_id=row["id"])
    await auth_repo.update_user_session(
        db,
        session_id=row["id"],
        refresh_token_hash=hash_refresh_token(refresh),
        expires_at=expires,
    )
    # Back-date last_used_at directly on the ORM row so the check fires.
    stale = (datetime.now(UTC) - last_used_delta).replace(tzinfo=None)
    db_row = (await db.execute(
        select(UserSession).where(UserSession.id == row["id"])
    )).scalar_one_or_none()
    assert db_row is not None
    db_row.last_used_at = stale  # type: ignore[assignment]
    await db.flush()
    return row["id"], refresh


# ---------------------------------------------------------------------------
# POST /auth/refresh — inactivity branch
# ---------------------------------------------------------------------------


async def test_refresh_within_window_succeeds(
    client: AsyncClient,
    db_session: AsyncSession,
    client_user: User,
) -> None:
    """Idle 2h on a 14-day cap — refresh must succeed."""
    _, refresh = await _seed_session(
        db_session, client_user.id, "client", last_used_delta=timedelta(hours=2)
    )
    client.cookies.set("refreshToken", refresh)

    resp = await client.post("/api/v1/auth/refresh")
    assert resp.status_code == 200


async def test_refresh_outside_default_window_rejected(
    client: AsyncClient,
    db_session: AsyncSession,
    client_user: User,
) -> None:
    """Client idle 15 days on a 14-day cap — refresh 401 + session deleted."""
    sid, refresh = await _seed_session(
        db_session, client_user.id, "client", last_used_delta=timedelta(days=15)
    )
    client.cookies.set("refreshToken", refresh)

    resp = await client.post("/api/v1/auth/refresh")
    assert resp.status_code == 401

    gone = (await db_session.execute(select(UserSession).where(UserSession.id == sid))).scalar_one_or_none()
    assert gone is None


async def test_refresh_outside_employee_window_rejected(
    client: AsyncClient,
    db_session: AsyncSession,
    employee_user: User,
) -> None:
    """Employee idle 4 days on a 3-day cap — refresh 401."""
    sid, refresh = await _seed_session(
        db_session,
        employee_user.id,
        "carcraft_employee",
        last_used_delta=timedelta(days=4),
    )
    client.cookies.set("refreshToken", refresh)

    resp = await client.post("/api/v1/auth/refresh")
    assert resp.status_code == 401

    gone = (await db_session.execute(select(UserSession).where(UserSession.id == sid))).scalar_one_or_none()
    assert gone is None


async def test_refresh_client_within_default_but_employee_cap_would_bite(
    client: AsyncClient,
    db_session: AsyncSession,
    client_user: User,
) -> None:
    """2 days idle: outside the 3-day employee cap, but client cap (14d) allows.

    Guards against a shared-window leak where the tighter employee bound
    accidentally rejects a normal user.
    """
    _, refresh = await _seed_session(
        db_session, client_user.id, "client", last_used_delta=timedelta(days=2)
    )
    client.cookies.set("refreshToken", refresh)

    resp = await client.post("/api/v1/auth/refresh")
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# GET /auth/sessions — active-device sweep
# ---------------------------------------------------------------------------


async def test_list_sessions_excludes_stale_rows_for_client(
    client: AsyncClient,
    db_session: AsyncSession,
    client_user: User,
    client_token: str,
) -> None:
    """A 15-day-idle row must not appear in the caller's active-device list."""
    fresh_sid, _ = await _seed_session(
        db_session, client_user.id, "client", last_used_delta=timedelta(hours=1)
    )
    stale_sid, _ = await _seed_session(
        db_session, client_user.id, "client", last_used_delta=timedelta(days=15)
    )

    resp = await client.get(
        "/api/v1/users/me/sessions", headers=_auth(client_token)
    )
    assert resp.status_code == 200
    ids = {row["id"] for row in resp.json()["sessions"]}
    assert str(fresh_sid) in ids
    assert str(stale_sid) not in ids


async def test_list_sessions_excludes_stale_rows_for_employee(
    client: AsyncClient,
    db_session: AsyncSession,
    employee_user: User,
    employee_token: str,
) -> None:
    """Employee sees the tighter 3-day cap in their own device list."""
    fresh_sid, _ = await _seed_session(
        db_session,
        employee_user.id,
        "carcraft_employee",
        last_used_delta=timedelta(hours=1),
    )
    stale_sid, _ = await _seed_session(
        db_session,
        employee_user.id,
        "carcraft_employee",
        last_used_delta=timedelta(days=4),
    )

    resp = await client.get(
        "/api/v1/users/me/sessions", headers=_auth(employee_token)
    )
    assert resp.status_code == 200
    ids = {row["id"] for row in resp.json()["sessions"]}
    assert str(fresh_sid) in ids
    assert str(stale_sid) not in ids
