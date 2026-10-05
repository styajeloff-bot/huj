"""Integration tests for DELETE /api/v1/auth/me (BE-5 GDPR erasure)."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID

import pytest
import sqlalchemy as sa
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.auth import generate_tokens, hash_refresh_token
from infrastructure.models.users import User, UserSession
from infrastructure.repositories import auth_repository as auth_repo
from infrastructure.settings import settings

pytestmark = pytest.mark.asyncio


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _seed_session(db: AsyncSession, user_id: UUID) -> UUID:
    """Create a persisted refresh session for ``user_id``; return its id."""
    expires = datetime.now(UTC) + timedelta(days=settings.refresh_token_expiry_days)
    row = await auth_repo.create_user_session(
        db,
        user_id=user_id,
        refresh_token_hash=hash_refresh_token("seed"),
        expires_at=expires,
    )
    return cast("UUID", row["id"])


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


async def test_delete_me_anonymizes_row_and_clears_cookies(
    client: AsyncClient,
    db_session: AsyncSession,
    client_user: User,
    client_token: str,
) -> None:
    sid = await _seed_session(db_session, client_user.id)
    original_phone = client_user.phone

    resp = await client.delete(
        "/api/v1/auth/me",
        headers=_auth(client_token),
        cookies={"accessToken": client_token},
    )
    assert resp.status_code == 200
    assert resp.json()["message"] == "Учётная запись удалена"

    # Cookies are cleared on the response
    set_cookies = resp.headers.get_list("set-cookie")
    assert any('accessToken=""' in h or "accessToken=;" in h for h in set_cookies)
    assert any('refreshToken=""' in h or "refreshToken=;" in h for h in set_cookies)

    # DB: user row is kept but PII is replaced / nulled. Re-query fresh to
    # avoid a stale ORM snapshot from the fixture.
    updated = (
        await db_session.execute(
            sa.select(User).where(User.id == client_user.id)
        )
    ).scalars().one()
    assert updated.is_active is False
    assert updated.name is None
    assert updated.email == f"anonymized-{str(client_user.id)[:12]}@deleted.local"
    assert updated.phone != original_phone
    assert updated.phone.startswith("+0000000")
    assert updated.mfa_enabled is False
    assert updated.mfa_secret is None
    assert updated.mfa_backup_codes is None

    # No sessions left for this user.
    row = await db_session.get(UserSession, sid)
    assert row is None
    remaining = (
        await db_session.execute(
            sa.select(UserSession).where(UserSession.user_id == client_user.id)
        )
    ).scalars().all()
    assert remaining == []


async def test_delete_me_revokes_access_token(
    client: AsyncClient,
    client_user: User,
    client_token: str,
) -> None:
    """After erasure the caller's access token lands on the denylist."""
    # Sanity: token is usable pre-erasure.
    ok = await client.get("/api/v1/auth/me", headers=_auth(client_token))
    assert ok.status_code == 200

    resp = await client.delete(
        "/api/v1/auth/me",
        headers=_auth(client_token),
        cookies={"accessToken": client_token},
    )
    assert resp.status_code == 200

    revoked = await client.get("/api/v1/auth/me", headers=_auth(client_token))
    assert revoked.status_code == 401
    assert revoked.json()["code"] == "TOKEN_REVOKED"


# ---------------------------------------------------------------------------
# Auth gating
# ---------------------------------------------------------------------------


async def test_delete_me_requires_auth(client: AsyncClient) -> None:
    resp = await client.delete("/api/v1/auth/me")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Idempotency — a second DELETE must still respond cleanly.
# ---------------------------------------------------------------------------


async def test_delete_me_is_idempotent(
    client: AsyncClient,
    client_user: User,
) -> None:
    """Second erasure must not explode.

    We chose a clean 200 "already erased" response over 4xx — the user's
    intent ("please erase my data") is satisfied either way, and a 4xx on
    retry leaks that the account existed. To exercise the second call with
    a still-valid JWT we mint fresh tokens around each call (the token
    issued before the first erasure is denylisted by it).
    """
    first_token, _ = generate_tokens(client_user.id, "client", None)
    resp1 = await client.delete(
        "/api/v1/auth/me",
        headers=_auth(first_token),
        cookies={"accessToken": first_token},
    )
    assert resp1.status_code == 200

    # A brand-new JWT for the same user_id — is_active is now False so
    # authenticate_access_token_with_db would reject, but the plain
    # get_current_user dependency only checks the JWT + denylist, which
    # still passes for a freshly minted token.
    second_token, _ = generate_tokens(client_user.id, "client", None)
    resp2 = await client.delete(
        "/api/v1/auth/me",
        headers=_auth(second_token),
        cookies={"accessToken": second_token},
    )
    assert resp2.status_code == 200
