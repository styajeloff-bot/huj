"""Integration tests for GET/DELETE /api/v1/users/me/sessions (F4/F5).

Scope of these tests (post Phase 9 R1):
 * ``GET /users/me/sessions`` returns only the caller's sessions.
 * ``DELETE /users/me/sessions/{id}`` revokes only the caller's session.
 * Attempting to delete another user's session returns 404 (no leak).
 * ``isCurrent`` is set to True for the session matching the
   ``refreshToken`` cookie, False otherwise.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

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


async def _issue_session(
    db: AsyncSession,
    user_id: UUID,
    *,
    ip: str | None = None,
    ua: str | None = None,
) -> tuple[UUID, str]:
    """Create a persisted session + a matching refresh JWT; return (sid, jwt)."""
    expires = datetime.now(UTC) + timedelta(days=settings.refresh_token_expiry_days)
    row = await auth_repo.create_user_session(
        db,
        user_id=user_id,
        refresh_token_hash=hash_refresh_token("seed"),
        expires_at=expires,
        ip_address=ip,
        user_agent=ua,
    )
    _, refresh = generate_tokens(user_id, "client", None, refresh_session_id=row["id"])
    await auth_repo.update_user_session(
        db,
        session_id=row["id"],
        refresh_token_hash=hash_refresh_token(refresh),
        expires_at=expires,
    )
    return row["id"], refresh


# ---------------------------------------------------------------------------
# GET /users/me/sessions
# ---------------------------------------------------------------------------


async def test_list_sessions_returns_only_own_rows(
    client: AsyncClient,
    db_session: AsyncSession,
    client_user: User,
    other_user: User,
    client_token: str,
) -> None:
    own_sid, _ = await _issue_session(db_session, client_user.id, ip="1.2.3.4", ua="A")
    await _issue_session(db_session, other_user.id, ip="9.9.9.9", ua="B")

    resp = await client.get("/api/v1/users/me/sessions", headers=_auth(client_token))
    assert resp.status_code == 200
    sessions = resp.json()["sessions"]

    ids = {s["id"] for s in sessions}
    assert str(own_sid) in ids
    # Other user's session must not leak
    other_row = (
        await db_session.execute(
            select(UserSession).where(UserSession.user_id == other_user.id)
        )
    ).scalars().one()
    assert str(other_row.id) not in ids


async def test_list_sessions_marks_is_current(
    client: AsyncClient,
    db_session: AsyncSession,
    client_user: User,
    client_token: str,
) -> None:
    sid1, refresh1 = await _issue_session(db_session, client_user.id, ip="1.1.1.1")
    sid2, _refresh2 = await _issue_session(db_session, client_user.id, ip="2.2.2.2")

    resp = await client.get(
        "/api/v1/users/me/sessions",
        headers=_auth(client_token),
        cookies={"refreshToken": refresh1},
    )
    assert resp.status_code == 200
    by_id = {s["id"]: s for s in resp.json()["sessions"]}
    assert by_id[str(sid1)]["isCurrent"] is True
    assert by_id[str(sid2)]["isCurrent"] is False


async def test_list_sessions_surfaces_metadata(
    client: AsyncClient,
    db_session: AsyncSession,
    client_user: User,
    client_token: str,
) -> None:
    sid, _ = await _issue_session(
        db_session, client_user.id, ip="10.0.0.7", ua="Mozilla/5.0 pytest"
    )
    resp = await client.get("/api/v1/users/me/sessions", headers=_auth(client_token))
    assert resp.status_code == 200
    sessions = resp.json()["sessions"]
    mine = next(s for s in sessions if s["id"] == str(sid))
    assert mine["ipAddress"] == "10.0.0.7"
    assert mine["userAgent"] == "Mozilla/5.0 pytest"


async def test_list_sessions_unauthenticated(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/users/me/sessions")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# DELETE /users/me/sessions/{id}
# ---------------------------------------------------------------------------


async def test_delete_own_session_succeeds(
    client: AsyncClient,
    db_session: AsyncSession,
    client_user: User,
    client_token: str,
) -> None:
    sid, _ = await _issue_session(db_session, client_user.id)

    resp = await client.delete(
        f"/api/v1/users/me/sessions/{sid}", headers=_auth(client_token)
    )
    assert resp.status_code == 204

    row = (await db_session.execute(
        select(UserSession).where(UserSession.id == sid)
    )).scalar_one_or_none()
    assert row is None


async def test_delete_other_users_session_returns_404(
    client: AsyncClient,
    db_session: AsyncSession,
    other_user: User,
    client_token: str,
) -> None:
    sid, _ = await _issue_session(db_session, other_user.id)

    resp = await client.delete(
        f"/api/v1/users/me/sessions/{sid}", headers=_auth(client_token)
    )
    assert resp.status_code == 404

    # Session must still exist — ownership check must not delete it.
    row = await db_session.get(UserSession, sid)
    assert row is not None


async def test_delete_unknown_session_returns_404(
    client: AsyncClient,
    client_token: str,
) -> None:
    resp = await client.delete(
        f"/api/v1/users/me/sessions/{uuid4()}", headers=_auth(client_token)
    )
    assert resp.status_code == 404


async def test_delete_session_unauthenticated(client: AsyncClient) -> None:
    resp = await client.delete("/api/v1/users/me/sessions/1")
    assert resp.status_code == 401
