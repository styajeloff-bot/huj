"""Integration tests for the MFA (TOTP) flow.

Covers setup → activation → login → disable, bad/expired tokens,
and single-use backup codes.
"""
from __future__ import annotations

from uuid import UUID

import pyotp
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from domain.services.scopes import roles_to_scopes
from infrastructure.auth import generate_tokens
from infrastructure.auth_stepup import issue_mfa_token
from infrastructure.models.users import User
from infrastructure.repositories import auth_repository as auth_repo
from infrastructure.services.totp import (
    generate_backup_codes,
    generate_secret,
    hash_backup_code,
)

pytestmark = pytest.mark.asyncio

_TEST_PHONE = "+76660004567"  # test_phone_user fixture
_CODE = "0000"


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _totp_now(secret: str) -> str:
    return pyotp.TOTP(secret).now()


async def _enable_mfa_for(
    db_session: AsyncSession,
    user_id: UUID,
    secret: str,
    backup_hashes: list[str] | None = None,
) -> None:
    await auth_repo.activate_mfa(
        db_session,
        user_id,
        secret,
        backup_hashes or [],
    )


# ---------------------------------------------------------------------------
# Setup → verify-setup → disable
# ---------------------------------------------------------------------------


async def test_mfa_setup_returns_secret_and_qr(
    client: AsyncClient,
    test_phone_user: User,
    test_phone_token: str,
) -> None:
    resp = await client.post(
        "/api/v1/auth/mfa",
        headers=_auth(test_phone_token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["secret"]) == 32
    assert data["otpauthUrl"].startswith("otpauth://totp/")
    assert data["qrPngBase64"]  # non-empty base64


async def test_mfa_verify_setup_activates_and_returns_backup_codes(
    client: AsyncClient,
    db_session: AsyncSession,
    test_phone_user: User,
    test_phone_token: str,
) -> None:
    setup = await client.post(
        "/api/v1/auth/mfa", headers=_auth(test_phone_token)
    )
    secret = setup.json()["secret"]

    resp = await client.put(
        "/api/v1/auth/mfa",
        headers=_auth(test_phone_token),
        json={"code": _totp_now(secret)},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["message"] == "MFA включена"
    assert len(data["backupCodes"]) == 8
    for code in data["backupCodes"]:
        assert len(code) == 10

    state = await auth_repo.get_mfa_state(db_session, test_phone_user.id)
    assert state is not None
    assert state["enabled"] is True
    assert state["secret"] == secret
    assert state["pending_secret"] is None
    assert len(state["backup_code_hashes"]) == 8


async def test_mfa_disable_requires_totp(
    client: AsyncClient,
    db_session: AsyncSession,
    test_phone_user: User,
    test_phone_token: str,
) -> None:
    secret = generate_secret()
    await _enable_mfa_for(db_session, test_phone_user.id, secret)

    bad = await client.request(
        "DELETE",
        "/api/v1/auth/mfa",
        headers=_auth(test_phone_token),
        json={"code": "000000"},
    )
    assert bad.status_code == 401

    ok = await client.request(
        "DELETE",
        "/api/v1/auth/mfa",
        headers=_auth(test_phone_token),
        json={"code": _totp_now(secret)},
    )
    assert ok.status_code == 200

    refreshed = (
        await db_session.execute(select(User).where(User.id == test_phone_user.id))
    ).scalars().one()
    assert refreshed.mfa_enabled is False
    assert refreshed.mfa_secret is None


# ---------------------------------------------------------------------------
# Login flow — without and with MFA
# ---------------------------------------------------------------------------


async def test_login_without_mfa_returns_full_tokens(
    client: AsyncClient,
    test_phone_user: User,
) -> None:
    await client.post("/api/v1/auth/login", json={"phone": _TEST_PHONE})
    resp = await client.post(
        "/api/v1/auth/verify-phone",
        json={"phone": _TEST_PHONE, "code": _CODE},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "user" in data
    assert data["user"]["scopes"] == roles_to_scopes("client")
    assert "accessToken" in resp.cookies
    assert "refreshToken" in resp.cookies


async def test_login_with_mfa_returns_step_up(
    client: AsyncClient,
    db_session: AsyncSession,
    test_phone_user: User,
) -> None:
    secret = generate_secret()
    await _enable_mfa_for(db_session, test_phone_user.id, secret)

    await client.post("/api/v1/auth/login", json={"phone": _TEST_PHONE})
    resp = await client.post(
        "/api/v1/auth/verify-phone",
        json={"phone": _TEST_PHONE, "code": _CODE},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["mfaRequired"] is True
    assert isinstance(data["mfaToken"], str)
    # No cookies set on half-session
    assert "accessToken" not in resp.cookies
    assert "refreshToken" not in resp.cookies

    verify = await client.post(
        "/api/v1/auth/mfa/verify",
        json={"mfaToken": data["mfaToken"], "code": _totp_now(secret)},
    )
    assert verify.status_code == 200
    assert verify.json()["user"]["scopes"] == roles_to_scopes("client")
    assert "accessToken" in verify.cookies
    assert "refreshToken" in verify.cookies


async def test_mfa_verify_bad_code_returns_invalid(
    client: AsyncClient,
    db_session: AsyncSession,
    test_phone_user: User,
) -> None:
    secret = generate_secret()
    await _enable_mfa_for(db_session, test_phone_user.id, secret)

    token = issue_mfa_token(test_phone_user.id)
    resp = await client.post(
        "/api/v1/auth/mfa/verify",
        json={"mfaToken": token, "code": "000000"},
    )
    assert resp.status_code == 401
    assert "MFA_INVALID_CODE" in resp.text


async def test_mfa_verify_backup_code_consumed_once(
    client: AsyncClient,
    db_session: AsyncSession,
    test_phone_user: User,
) -> None:
    secret = generate_secret()
    pairs = generate_backup_codes(n=2)
    plain_codes = [p for p, _ in pairs]
    hashes = [h for _, h in pairs]
    await _enable_mfa_for(db_session, test_phone_user.id, secret, hashes)

    token1 = issue_mfa_token(test_phone_user.id)
    first = await client.post(
        "/api/v1/auth/mfa/verify",
        json={"mfaToken": token1, "code": plain_codes[0]},
    )
    assert first.status_code == 200

    # Re-using the same backup code must fail.
    token2 = issue_mfa_token(test_phone_user.id)
    second = await client.post(
        "/api/v1/auth/mfa/verify",
        json={"mfaToken": token2, "code": plain_codes[0]},
    )
    assert second.status_code == 401

    # The other backup code is still valid.
    state = await auth_repo.get_mfa_state(db_session, test_phone_user.id)
    assert state is not None
    assert hash_backup_code(plain_codes[0]) not in state["backup_code_hashes"]
    assert hash_backup_code(plain_codes[1]) in state["backup_code_hashes"]


async def test_mfa_expired_token_rejected(
    client: AsyncClient,
    db_session: AsyncSession,
    test_phone_user: User,
) -> None:
    secret = generate_secret()
    await _enable_mfa_for(db_session, test_phone_user.id, secret)

    # Craft an already-expired token using the same HS256 path as the real
    # issuer but with an ``exp`` in the past.
    from datetime import UTC, datetime, timedelta

    from jose import jwt

    from infrastructure.settings import settings

    now = datetime.now(UTC)
    expired = jwt.encode(
        {
            "userId": str(test_phone_user.id),
            "purpose": "mfa_step_up",
            "jti": "expired",
            "iat": now - timedelta(minutes=30),
            "exp": now - timedelta(minutes=25),
        },
        settings.jwt_access_secret,
        algorithm="HS256",
    )

    resp = await client.post(
        "/api/v1/auth/mfa/verify",
        json={"mfaToken": expired, "code": _totp_now(secret)},
    )
    assert resp.status_code == 401
    assert "MFA_TOKEN_EXPIRED" in resp.text


async def test_mfa_setup_rejected_when_already_enabled(
    client: AsyncClient,
    db_session: AsyncSession,
    test_phone_user: User,
    test_phone_token: str,
) -> None:
    secret = generate_secret()
    await _enable_mfa_for(db_session, test_phone_user.id, secret)

    resp = await client.post(
        "/api/v1/auth/mfa",
        headers=_auth(test_phone_token),
    )
    assert resp.status_code == 409


async def test_mfa_endpoints_require_auth(client: AsyncClient) -> None:
    assert (await client.post("/api/v1/auth/mfa")).status_code == 401
    assert (
        await client.put("/api/v1/auth/mfa", json={"code": "123456"})
    ).status_code == 401
    assert (
        await client.request(
            "DELETE", "/api/v1/auth/mfa", json={"code": "123456"}
        )
    ).status_code == 401


async def test_employee_with_mfa_gets_step_up(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """carcraft_employee role also goes through the MFA half-session on login."""
    user = User(
        phone="+76660004569",
        email="employee-mfa@test.local",
        name="Employee MFA",
        role="carcraft_employee",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)

    secret = generate_secret()
    await _enable_mfa_for(db_session, user.id, secret)

    # Access token for the "already-authenticated" path isn't needed here —
    # we're exercising verify-phone.
    _ = generate_tokens(user.id, "carcraft_employee", None)

    await client.post("/api/v1/auth/login", json={"phone": user.phone})
    resp = await client.post(
        "/api/v1/auth/verify-phone",
        json={"phone": user.phone, "code": _CODE},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["mfaRequired"] is True


# ---------------------------------------------------------------------------
# R8 consolidated surface — GET /mfa (status) + POST /mfa/backup-codes
# ---------------------------------------------------------------------------


async def test_mfa_status_disabled_by_default(
    client: AsyncClient,
    test_phone_user: User,
    test_phone_token: str,
) -> None:
    resp = await client.get("/api/v1/auth/mfa", headers=_auth(test_phone_token))
    assert resp.status_code == 200
    data = resp.json()
    assert data["enabled"] is False
    assert data["method"] is None
    assert data["hasBackupCodes"] is False
    assert data["backupCodesRemaining"] is None


async def test_mfa_status_enabled_reports_backup_codes(
    client: AsyncClient,
    db_session: AsyncSession,
    test_phone_user: User,
    test_phone_token: str,
) -> None:
    secret = generate_secret()
    await _enable_mfa_for(
        db_session,
        test_phone_user.id,
        secret,
        backup_hashes=["h1", "h2", "h3"],
    )
    resp = await client.get("/api/v1/auth/mfa", headers=_auth(test_phone_token))
    assert resp.status_code == 200
    data = resp.json()
    assert data["enabled"] is True
    assert data["method"] == "totp"
    assert data["hasBackupCodes"] is True
    assert data["backupCodesRemaining"] == 3


async def test_mfa_regenerate_backup_codes_replaces_existing(
    client: AsyncClient,
    db_session: AsyncSession,
    test_phone_user: User,
    test_phone_token: str,
) -> None:
    secret = generate_secret()
    await _enable_mfa_for(
        db_session,
        test_phone_user.id,
        secret,
        backup_hashes=["h1", "h2"],
    )
    resp = await client.post(
        "/api/v1/auth/mfa/backup-codes",
        headers=_auth(test_phone_token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["backupCodes"]) == 8

    state = await auth_repo.get_mfa_state(db_session, test_phone_user.id)
    assert state is not None
    assert len(state["backup_code_hashes"]) == 8
    # Old hashes are gone.
    assert "h1" not in state["backup_code_hashes"]
    assert "h2" not in state["backup_code_hashes"]


async def test_mfa_regenerate_rejected_when_mfa_disabled(
    client: AsyncClient,
    test_phone_user: User,
    test_phone_token: str,
) -> None:
    resp = await client.post(
        "/api/v1/auth/mfa/backup-codes",
        headers=_auth(test_phone_token),
    )
    assert resp.status_code == 400
