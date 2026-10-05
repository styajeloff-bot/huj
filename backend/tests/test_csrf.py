"""End-to-end tests for the double-submit-cookie CSRF middleware.

Middleware lives in ``presentation/middleware/csrf.py``. In production the
middleware is feature-flagged off (``settings.csrf_enabled=False``) until
the frontend plugin ships to every client. These tests flip it on per-test
via monkeypatch and verify the full matrix of allow/deny paths.
"""
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.auth import generate_tokens, hash_refresh_token
from infrastructure.models.users import User
from infrastructure.repositories import auth_repository as auth_repo
from infrastructure.settings import settings

pytestmark = pytest.mark.asyncio


@pytest.fixture
def csrf_on(monkeypatch: pytest.MonkeyPatch) -> None:
    """Flip csrf_enabled on for the duration of the test."""
    monkeypatch.setattr(settings, "csrf_enabled", True)


async def _seed_refresh_session(db_session: AsyncSession, user_id: UUID) -> str:
    """Create a real refresh-session row and return the signed refresh token."""
    expires_at = datetime.now(UTC) + timedelta(days=settings.refresh_token_expiry_days)
    row = await auth_repo.create_user_session(
        db_session,
        user_id=user_id,
        refresh_token_hash=hash_refresh_token("seed"),
        expires_at=expires_at,
    )
    _, refresh = generate_tokens(user_id, "client", None, refresh_session_id=row["id"])
    await auth_repo.update_user_session(
        db_session,
        session_id=row["id"],
        refresh_token_hash=hash_refresh_token(refresh),
        expires_at=expires_at,
    )
    return refresh


# ---------------------------------------------------------------------------
# Happy path — cookie + header match
# ---------------------------------------------------------------------------


async def test_csrf_mutating_with_matching_cookie_and_header_passes(
    csrf_on: None,
    client: AsyncClient,
    client_user: User,
    db_session: AsyncSession,
) -> None:
    """POST with accessToken cookie + matching X-CSRF-Token → passes CSRF gate."""
    access_token, _ = generate_tokens(client_user.id, "client", None)
    refresh_token = await _seed_refresh_session(db_session, client_user.id)

    resp = await client.post(
        "/api/v1/auth/logout",
        cookies={
            "accessToken": access_token,
            "refreshToken": refresh_token,
            settings.csrf_cookie_name: "matching-token",
        },
        headers={settings.csrf_header_name: "matching-token"},
    )
    # Logout itself returns 200; if CSRF blocked it we'd see 403.
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Deny paths — missing / mismatched / absent header
# ---------------------------------------------------------------------------


async def test_csrf_mutating_without_header_is_blocked(
    csrf_on: None,
    client: AsyncClient,
    client_user: User,
) -> None:
    """POST with accessToken cookie but NO X-CSRF-Token header → 403."""
    access_token, _ = generate_tokens(client_user.id, "client", None)

    resp = await client.post(
        "/api/v1/auth/logout",
        cookies={
            "accessToken": access_token,
            settings.csrf_cookie_name: "some-value",
        },
    )
    assert resp.status_code == 403
    body = resp.json()
    assert body["code"] == "CSRF_INVALID"


async def test_csrf_mutating_with_mismatched_header_is_blocked(
    csrf_on: None,
    client: AsyncClient,
    client_user: User,
) -> None:
    """Cookie says X but header says Y → 403."""
    access_token, _ = generate_tokens(client_user.id, "client", None)

    resp = await client.post(
        "/api/v1/auth/logout",
        cookies={
            "accessToken": access_token,
            settings.csrf_cookie_name: "value-A",
        },
        headers={settings.csrf_header_name: "value-B"},
    )
    assert resp.status_code == 403
    assert resp.json()["code"] == "CSRF_INVALID"


async def test_csrf_mutating_without_cookie_is_not_checked(
    csrf_on: None,
    client: AsyncClient,
) -> None:
    """No accessToken cookie → request is unauthenticated from CSRF's view and skipped.

    Login is unauthenticated and has its own rate-limiter / business errors
    — CSRF must NOT block it. (We're testing that CSRF doesn't interfere,
    not the login's own outcome.)
    """
    resp = await client.post(
        "/api/v1/auth/login",
        json={"phone": "+76660004568"},
    )
    # Whatever the business outcome is, it must NOT be a CSRF 403.
    if resp.status_code == 403:
        assert resp.json().get("code") != "CSRF_INVALID"


# ---------------------------------------------------------------------------
# Safe-method bypass
# ---------------------------------------------------------------------------


async def test_csrf_safe_methods_pass_without_header(
    csrf_on: None,
    client: AsyncClient,
    client_user: User,
) -> None:
    """GET with accessToken cookie but no CSRF header → still succeeds."""
    access_token, _ = generate_tokens(client_user.id, "client", None)

    resp = await client.get(
        "/api/v1/auth/me",
        cookies={"accessToken": access_token},
    )
    # /me is authenticated; CSRF must not block a GET regardless of headers.
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Exempt paths
# ---------------------------------------------------------------------------


async def test_csrf_webhook_path_is_exempt(
    csrf_on: None,
    client: AsyncClient,
) -> None:
    """ModulBank webhooks authenticate via signature — CSRF must not interfere.

    We don't care about the business response here; we only assert the
    middleware didn't return CSRF_INVALID.
    """
    resp = await client.post(
        "/api/v1/payments/webhook/modulbank",
        data={"order_id": "CARCRAFT-1", "status": "success", "signature": "x"},
    )
    if resp.status_code == 403:
        assert resp.json().get("code") != "CSRF_INVALID"


# ---------------------------------------------------------------------------
# Feature flag off — middleware no-ops
# ---------------------------------------------------------------------------


async def test_csrf_disabled_allows_mutating_without_header(
    client: AsyncClient,
    client_user: User,
) -> None:
    """With csrf_enabled=False (default), no checks happen."""
    # Do NOT apply csrf_on — test the default-off behavior.
    access_token, _ = generate_tokens(client_user.id, "client", None)

    resp = await client.post(
        "/api/v1/auth/logout",
        cookies={"accessToken": access_token},
    )
    assert resp.status_code == 200
