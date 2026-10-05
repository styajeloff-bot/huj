"""Integration tests for mandatory MFA enforcement (E1).

Covers the branch in ``handle_verify_phone`` that forces privileged roles
without MFA enrolment into a setup flow — plus the new
``POST /auth/mfa/init-setup`` and ``POST /auth/mfa/complete-setup``
endpoints that run inside the half-session before the user has a full
access token.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pyotp
import pytest
from httpx import AsyncClient
from jose import jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from domain.services.scopes import roles_to_scopes
from infrastructure.auth_stepup import build_mfa_setup_token
from infrastructure.models.users import User
from infrastructure.repositories import auth_repository as auth_repo
from infrastructure.services.totp import (
    generate_secret,
)
from infrastructure.settings import settings

pytestmark = pytest.mark.asyncio

_TEST_CLIENT_PHONE = "+76660004567"  # test_phone_user fixture (client)
_EMPLOYEE_PHONE = "+76660004568"     # test phone slot — employee
_CODE = "0000"


def _totp_now(secret: str) -> str:
    return pyotp.TOTP(secret).now()


async def _make_employee(db_session: AsyncSession, phone: str) -> User:
    user = User(
        phone=phone,
        email=f"emp-{phone[-4:]}@test.local",
        name="Employee Without MFA",
        role="carcraft_employee",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


# ---------------------------------------------------------------------------
# verify-phone branches
# ---------------------------------------------------------------------------


async def test_client_without_mfa_gets_full_tokens(
    client: AsyncClient,
    test_phone_user: User,
) -> None:
    """Non-privileged role (client) bypasses the mandatory-setup check."""
    await client.post("/api/v1/auth/login", json={"phone": _TEST_CLIENT_PHONE})
    resp = await client.post(
        "/api/v1/auth/verify-phone",
        json={"phone": _TEST_CLIENT_PHONE, "code": _CODE},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "user" in data
    assert "mfaSetupRequired" not in data
    assert "mfaRequired" not in data
    assert "accessToken" in resp.cookies
    assert "refreshToken" in resp.cookies


async def test_employee_with_mfa_enabled_gets_step_up(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Employee with MFA already on still takes the step-up (existing) path."""
    user = await _make_employee(db_session, _EMPLOYEE_PHONE)
    secret = generate_secret()
    await auth_repo.activate_mfa(db_session, user.id, secret, [])

    await client.post("/api/v1/auth/login", json={"phone": user.phone})
    resp = await client.post(
        "/api/v1/auth/verify-phone",
        json={"phone": user.phone, "code": _CODE},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("mfaRequired") is True
    assert isinstance(data.get("mfaToken"), str)
    assert "mfaSetupRequired" not in data


# ---------------------------------------------------------------------------
# POST /auth/mfa/complete-setup
# ---------------------------------------------------------------------------


async def test_complete_setup_with_valid_token_and_code(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Valid setupToken + fresh TOTP => MFA activated, cookies + backup codes."""
    user = await _make_employee(db_session, _EMPLOYEE_PHONE)

    secret = generate_secret()
    # Emulate the "client already saw the QR and stashed the pending secret"
    # step — in the real flow the frontend calls a setup endpoint during the
    # half-session. The pending secret is what complete-setup activates.
    await auth_repo.set_pending_mfa_secret(db_session, user.id, secret)

    setup_token = build_mfa_setup_token(user.id)

    resp = await client.put(
        "/api/v1/auth/mfa",
        json={"setupToken": setup_token, "code": _totp_now(secret)},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["user"]["role"] == "carcraft_employee"
    assert data["user"]["scopes"] == roles_to_scopes("carcraft_employee")
    assert isinstance(data["backupCodes"], list)
    assert len(data["backupCodes"]) == 8
    assert "accessToken" in resp.cookies
    assert "refreshToken" in resp.cookies

    refreshed = (
        await db_session.execute(select(User).where(User.id == user.id))
    ).scalars().one()
    assert refreshed.mfa_enabled is True
    assert refreshed.mfa_secret == secret
    assert refreshed.mfa_pending_secret is None


async def test_complete_setup_with_expired_token(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """An expired setupToken is rejected with 401 MFA_SETUP_TOKEN_EXPIRED."""
    user = await _make_employee(db_session, _EMPLOYEE_PHONE)
    secret = generate_secret()
    await auth_repo.set_pending_mfa_secret(db_session, user.id, secret)

    now = datetime.now(UTC)
    expired = jwt.encode(
        {
            "userId": str(user.id),
            "purpose": "mfa_setup",
            "jti": "expired-setup",
            "iat": now - timedelta(minutes=30),
            "exp": now - timedelta(minutes=15),
        },
        settings.jwt_access_secret,
        algorithm="HS256",
    )

    resp = await client.put(
        "/api/v1/auth/mfa",
        json={"setupToken": expired, "code": _totp_now(secret)},
    )
    assert resp.status_code == 401
    assert "MFA_SETUP_TOKEN_EXPIRED" in resp.text


async def test_complete_setup_when_mfa_already_enabled_returns_409(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """If MFA is already active (double-submit or admin enrolment raced us),
    the mandatory-setup endpoint must refuse — chose 409 Conflict to match
    the existing /mfa/setup policy for an already-enabled user.
    """
    user = await _make_employee(db_session, _EMPLOYEE_PHONE)
    secret = generate_secret()
    # User is fully enrolled already.
    await auth_repo.activate_mfa(db_session, user.id, secret, [])

    setup_token = build_mfa_setup_token(user.id)
    resp = await client.put(
        "/api/v1/auth/mfa",
        json={"setupToken": setup_token, "code": _totp_now(secret)},
    )
    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# POST /auth/mfa/init-setup — QR fetch during the half-session
# ---------------------------------------------------------------------------


async def test_init_setup_returns_qr_and_stashes_pending_secret(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Valid setupToken => server generates secret + returns QR; DB has pending_secret."""
    user = await _make_employee(db_session, _EMPLOYEE_PHONE)
    setup_token = build_mfa_setup_token(user.id)

    resp = await client.post(
        "/api/v1/auth/mfa",
        json={"setupToken": setup_token},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data["secret"], str) and len(data["secret"]) >= 16
    assert data["otpauthUrl"].startswith("otpauth://totp/")
    assert isinstance(data["qrPngBase64"], str) and data["qrPngBase64"]

    refreshed = (
        await db_session.execute(select(User).where(User.id == user.id))
    ).scalars().one()
    assert refreshed.mfa_pending_secret == data["secret"]
    assert refreshed.mfa_enabled is False


async def test_init_setup_round_trips_to_complete_setup(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """init-setup → user scans → complete-setup: full mandatory-enrolment happy path."""
    user = await _make_employee(db_session, _EMPLOYEE_PHONE)
    setup_token = build_mfa_setup_token(user.id)

    init = await client.post(
        "/api/v1/auth/mfa",
        json={"setupToken": setup_token},
    )
    assert init.status_code == 200
    secret = init.json()["secret"]

    complete = await client.put(
        "/api/v1/auth/mfa",
        json={"setupToken": setup_token, "code": _totp_now(secret)},
    )
    assert complete.status_code == 200
    assert "accessToken" in complete.cookies


async def test_init_setup_with_expired_token(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Expired setupToken → 401 MFA_SETUP_TOKEN_EXPIRED, no pending secret written."""
    user = await _make_employee(db_session, _EMPLOYEE_PHONE)

    now = datetime.now(UTC)
    expired = jwt.encode(
        {
            "userId": str(user.id),
            "purpose": "mfa_setup",
            "jti": "expired-init",
            "iat": now - timedelta(minutes=30),
            "exp": now - timedelta(minutes=15),
        },
        settings.jwt_access_secret,
        algorithm="HS256",
    )
    resp = await client.post(
        "/api/v1/auth/mfa",
        json={"setupToken": expired},
    )
    assert resp.status_code == 401
    assert "MFA_SETUP_TOKEN_EXPIRED" in resp.text

    refreshed = (
        await db_session.execute(select(User).where(User.id == user.id))
    ).scalars().one()
    assert refreshed.mfa_pending_secret is None


async def test_init_setup_rejected_when_mfa_already_enabled(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """User already has MFA active — init-setup returns 409."""
    user = await _make_employee(db_session, _EMPLOYEE_PHONE)
    await auth_repo.activate_mfa(db_session, user.id, generate_secret(), [])

    setup_token = build_mfa_setup_token(user.id)
    resp = await client.post(
        "/api/v1/auth/mfa",
        json={"setupToken": setup_token},
    )
    assert resp.status_code == 409
