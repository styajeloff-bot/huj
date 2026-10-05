"""Integration tests for DELETE /api/v1/users/{id}/mfa (admin-initiated MFA reset).

Covers the SecOps / support "account recovery" surface:
 * Employee with `auth:admin` can reset MFA of any user → MFA cleared,
   every session of the target killed, audit event emitted.
 * Clients (no scope) receive 403 INSUFFICIENT_PERMISSIONS.
 * Resetting when MFA is disabled on the target → 400 (refuse no-ops
   so audit trails can't be padded with meaningless resets).
 * Resetting an unknown user → 404.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.auth import hash_refresh_token
from infrastructure.messaging import auth_events
from infrastructure.models.users import User, UserSession
from infrastructure.repositories import auth_repository as auth_repo
from infrastructure.services.totp import generate_secret
from infrastructure.settings import settings

pytestmark = pytest.mark.asyncio


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _seed_session(db: AsyncSession, user_id: UUID) -> UUID:
    expires = datetime.now(UTC) + timedelta(days=settings.refresh_token_expiry_days)
    row = await auth_repo.create_user_session(
        db,
        user_id=user_id,
        refresh_token_hash=hash_refresh_token("seed-mfa-reset"),
        expires_at=expires,
        ip_address="8.8.8.8",
        user_agent="pytest-admin-mfa-reset",
    )
    return cast("UUID", row["id"])


async def _enable_mfa(db: AsyncSession, user_id: UUID) -> str:
    secret = generate_secret()
    await auth_repo.activate_mfa(db, user_id, secret, ["hash1", "hash2"])
    return secret


# ---------------------------------------------------------------------------
# Success path
# ---------------------------------------------------------------------------


async def test_employee_resets_mfa_wipes_state_and_sessions(
    client: AsyncClient,
    db_session: AsyncSession,
    client_user: User,
    employee_token: str,
) -> None:
    await _enable_mfa(db_session, client_user.id)
    await _seed_session(db_session, client_user.id)
    await _seed_session(db_session, client_user.id)

    resp = await client.request(
        "DELETE",
        f"/api/v1/users/{client_user.id}/mfa",
        headers=_auth(employee_token),
        json={"reason": "SUPPORT-1234: lost phone + authenticator"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["message"] == "MFA сброшена"
    assert body["sessionsKilled"] == 2

    refreshed = (
        await db_session.execute(select(User).where(User.id == client_user.id))
    ).scalars().one()
    assert refreshed.mfa_enabled is False
    assert refreshed.mfa_secret is None
    assert refreshed.mfa_pending_secret is None
    # JSONB column returns None after disable_mfa
    assert not refreshed.mfa_backup_codes

    remaining = (
        await db_session.execute(
            select(UserSession).where(UserSession.user_id == client_user.id)
        )
    ).scalars().all()
    assert remaining == []


# ---------------------------------------------------------------------------
# Authorization
# ---------------------------------------------------------------------------


async def test_client_cannot_reset_mfa(
    client: AsyncClient,
    db_session: AsyncSession,
    client_user: User,
    other_user: User,
    client_token: str,
) -> None:
    await _enable_mfa(db_session, other_user.id)

    resp = await client.request(
        "DELETE",
        f"/api/v1/users/{other_user.id}/mfa",
        headers=_auth(client_token),
        json={"reason": "sneaky sneaky"},
    )
    assert resp.status_code == 403
    assert resp.json()["code"] == "INSUFFICIENT_PERMISSIONS"

    # State unchanged.
    state = await auth_repo.get_mfa_state(db_session, other_user.id)
    assert state is not None
    assert state["enabled"] is True


async def test_reset_mfa_unauthenticated(
    client: AsyncClient,
    client_user: User,
) -> None:
    resp = await client.request(
        "DELETE",
        f"/api/v1/users/{client_user.id}/mfa",
        json={"reason": "anonymous"},
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Business rule violations
# ---------------------------------------------------------------------------


async def test_reset_mfa_when_not_enabled_returns_400(
    client: AsyncClient,
    client_user: User,
    employee_token: str,
) -> None:
    # client_user has MFA disabled by default.
    resp = await client.request(
        "DELETE",
        f"/api/v1/users/{client_user.id}/mfa",
        headers=_auth(employee_token),
        json={"reason": "SUPPORT-0000"},
    )
    assert resp.status_code == 400


async def test_reset_mfa_unknown_user_returns_404(
    client: AsyncClient,
    employee_token: str,
) -> None:
    resp = await client.request(
        "DELETE",
        f"/api/v1/users/{uuid4()}/mfa",
        headers=_auth(employee_token),
        json={"reason": "SUPPORT-0001"},
    )
    assert resp.status_code == 404


async def test_reset_mfa_rejects_too_short_reason(
    client: AsyncClient,
    db_session: AsyncSession,
    client_user: User,
    employee_token: str,
) -> None:
    await _enable_mfa(db_session, client_user.id)

    resp = await client.request(
        "DELETE",
        f"/api/v1/users/{client_user.id}/mfa",
        headers=_auth(employee_token),
        json={"reason": "a"},
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Audit event
# ---------------------------------------------------------------------------


async def test_reset_mfa_emits_audit_event(
    client: AsyncClient,
    db_session: AsyncSession,
    client_user: User,
    employee_user: User,
    employee_token: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _enable_mfa(db_session, client_user.id)
    await _seed_session(db_session, client_user.id)

    calls: list[tuple[str, dict]] = []

    def _spy(event: str, /, **fields: object) -> None:
        calls.append((event, dict(fields)))

    monkeypatch.setattr(auth_events, "emit", _spy)

    resp = await client.request(
        "DELETE",
        f"/api/v1/users/{client_user.id}/mfa",
        headers=_auth(employee_token),
        json={"reason": "TICKET-42"},
    )
    assert resp.status_code == 200

    reset_calls = [c for c in calls if c[0] == auth_events.ADMIN_MFA_RESET]
    assert len(reset_calls) == 1
    _, fields = reset_calls[0]
    assert fields["target_user_id"] == client_user.id
    assert fields["by_user_id"] == employee_user.id
    assert fields["reason"] == "TICKET-42"
    assert fields["sessions_killed"] == 1
