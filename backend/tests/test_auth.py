"""Integration tests for the auth API.

Uses test phone numbers (+777****4567...) where verification code is always '0000'
and SMS is never actually sent. Each test runs inside a rolled-back transaction.
"""
from datetime import UTC, datetime, timedelta
from typing import cast
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from application import authentication as authentication_service
from application.errors import ServiceError
from domain.services.scopes import roles_to_scopes
from infrastructure.auth import (
    decode_refresh_token,
    generate_tokens,
    hash_refresh_token,
)
from infrastructure.models.companies import Company
from infrastructure.models.users import CompanySelectHistory, User, UserCompany
from infrastructure.repositories import auth_repository as auth_repo
from infrastructure.settings import settings
from presentation.schemas.auth import UserOut

pytestmark = pytest.mark.asyncio

# Test phones from infrastructure/services/sms.py — code is always '0000'
_NEW_PHONE = "+76660004568"   # not registered
_CODE = "0000"


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


_COMPANY = {
    "name": "Test Company",
    "inn": "1234567890",
    "kpp": "123456789",
    "ogrn": "1234567890123",
    "legal_address": "Минск, ул. Тестовая, 1",
    "actual_address": "Минск, ул. Тестовая, 1",
    "phone": "+375291112233",
    "email": "company@test.local",
    "manager_name": "Ivan Ivanov",
    "entity_type": "other",
}


async def _issue_refresh_token(
    db_session: AsyncSession,
    user_id: UUID,
) -> str:
    expires_at = datetime.now(UTC) + timedelta(days=settings.refresh_token_expiry_days)
    user_session = await auth_repo.create_user_session(
        db_session,
        user_id=user_id,
        refresh_token_hash=hash_refresh_token("seed"),
        expires_at=expires_at,
    )
    _, refresh = generate_tokens(
        user_id,
        "client",
        None,
        refresh_session_id=user_session["id"],
    )
    await auth_repo.update_user_session(
        db_session,
        session_id=user_session["id"],
        refresh_token_hash=hash_refresh_token(refresh),
        expires_at=expires_at,
    )
    return cast("str", refresh)


# ===========================================================================
# POST /api/v1/auth/register
# ===========================================================================


async def test_register_without_code_creates_user_and_requests_verification(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    resp = await client.post(
        "/api/v1/auth/register",
        json={"phone": _NEW_PHONE, "name": "New User", "companies": [_COMPANY]},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["requiresVerification"] is True
    assert data["phone"] == _NEW_PHONE

    user = (
        await db_session.execute(select(User).where(User.phone == _NEW_PHONE))
    ).scalars().one()
    assert user.company_id is not None
    assert user.phone_verified is False

    links = (
        await db_session.execute(select(UserCompany).where(UserCompany.user_id == user.id))
    ).scalars().all()
    assert len(links) == 1
    assert links[0].sub_role == "administrator"
    assert links[0].can_view_applications is True
    assert links[0].can_create_applications is True

    selection = await db_session.get(CompanySelectHistory, user.id)
    assert selection is not None
    assert selection.company_id == user.company_id

    company = (
        await db_session.execute(select(Company).where(Company.inn == _COMPANY["inn"]))
    ).scalars().one()
    assert company.enrichment_status == "pending"


async def test_register_existing_company_links_user_as_blocked_employee(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    existing = Company(
        name="Existing Company",
        inn="9988776655",
        company_type="other",
        is_active=True,
    )
    db_session.add(existing)
    await db_session.flush()

    payload = {
        **_COMPANY,
        "name": existing.name,
        "inn": existing.inn,
    }
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "phone": "+76660004569",
            "name": "Existing Company User",
            "companies": [payload],
        },
    )
    assert resp.status_code == 201

    user = (
        await db_session.execute(select(User).where(User.phone == "+76660004569"))
    ).scalars().one()
    link = (
        await db_session.execute(
            select(UserCompany).where(
                UserCompany.user_id == user.id,
                UserCompany.company_id == existing.id,
            )
        )
    ).scalars().one()
    assert link.sub_role == "employee"
    assert link.can_view_applications is False
    assert link.can_create_applications is False


async def test_register_with_code_completes_auth(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    await client.post("/api/v1/auth/login", json={"phone": _NEW_PHONE})

    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "phone": _NEW_PHONE,
            "name": "Verified User",
            "email": "verified@test.local",
            "companies": [_COMPANY],
            "code": _CODE,
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["message"] == "Регистрация завершена"
    assert data["user"]["phone"] == _NEW_PHONE
    assert data["user"]["sub_role"] == "administrator"
    assert data["user"]["can_view_applications"] is True
    assert data["user"]["can_create_applications"] is True
    assert "accessToken" in resp.cookies
    assert "refreshToken" in resp.cookies

    user = (
        await db_session.execute(select(User).where(User.phone == _NEW_PHONE))
    ).scalars().one()
    assert user.phone_verified is True


async def test_register_existing_phone_conflict(
    client: AsyncClient,
    test_phone_user: User,
) -> None:
    resp = await client.post(
        "/api/v1/auth/register",
        json={"phone": test_phone_user.phone, "companies": [_COMPANY]},
    )
    assert resp.status_code == 409
    assert resp.json()["detail"] == "Введеный номер уже зарегистрирован на платформе"


async def test_register_new_company_for_existing_user_with_code(
    client: AsyncClient,
    db_session: AsyncSession,
    test_phone_user: User,
) -> None:
    await client.post("/api/v1/auth/login", json={"phone": test_phone_user.phone})

    new_company_payload = {
        **_COMPANY,
        "name": "Second Company LLC",
        "inn": "7701234567",
    }

    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "phone": test_phone_user.phone,
            "code": _CODE,
            "companies": [new_company_payload],
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["message"] == "Компании успешно добавлены"
    assert data["user"]["id"] == str(test_phone_user.id)
    assert data["user"]["phone"] == test_phone_user.phone
    assert "accessToken" in resp.cookies
    assert "refreshToken" in resp.cookies

    user = await db_session.get(User, test_phone_user.id)
    assert user is not None
    assert user.id == test_phone_user.id

    links = (
        await db_session.execute(
            select(UserCompany).where(UserCompany.user_id == test_phone_user.id)
        )
    ).scalars().all()
    company_in_db = (
        await db_session.execute(
            select(Company).where(Company.inn == new_company_payload["inn"])
        )
    ).scalars().one()
    linked_company_ids = {link.company_id for link in links}
    assert company_in_db.id in linked_company_ids
    assert any(
        c["id"] == str(company_in_db.id) for c in data["user"]["available_companies"]
    )



# ===========================================================================
# POST /api/v1/auth/login
# ===========================================================================


async def test_login_existing_user(
    client: AsyncClient,
    test_phone_user: User,
) -> None:
    """Login with existing user — 200, requiresVerification."""
    resp = await client.post(
        "/api/v1/auth/login",
        json={"phone": test_phone_user.phone},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["requiresVerification"] is True
    assert data["phone"] == test_phone_user.phone


async def test_login_nonexistent_user(client: AsyncClient) -> None:
    """Login with unknown phone — 404, requiresRegistration."""
    resp = await client.post(
        "/api/v1/auth/login",
        json={"phone": _NEW_PHONE},
    )
    assert resp.status_code == 404
    assert resp.json()["requiresRegistration"] is True


async def test_login_invalid_phone(client: AsyncClient) -> None:
    """Malformed phone — 422."""
    resp = await client.post("/api/v1/auth/login", json={"phone": "bad"})
    assert resp.status_code == 422


async def test_login_cooldown(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Second login within cooldown — 403, codeAlreadySent.

    Uses a real (non-test) phone so the cooldown fires.  SMS sending is
    monkeypatched to prevent any network calls.
    """
    real_phone = "+79001112233"
    user = User(
        phone=real_phone,
        email="cooldown@test.local",
        name="Cooldown User",
        role="client",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()

    # Prevent real SMTP from being called for a non-test phone.
    monkeypatch.setattr(
        "application.commands.auth._send_sms_background",
        AsyncMock(),
    )

    resp1 = await client.post("/api/v1/auth/login", json={"phone": real_phone})
    assert resp1.status_code == 200

    resp2 = await client.post("/api/v1/auth/login", json={"phone": real_phone})
    assert resp2.status_code == 403
    assert resp2.json()["codeAlreadySent"] is True


async def test_login_no_cooldown_for_test_phone(
    client: AsyncClient,
    test_phone_user: User,
) -> None:
    """Test phones (+7666…) are exempt from the 60-second cooldown.

    Two consecutive /login calls must both return 200 — the second one
    overwrites the existing verification_codes row instead of blocking.
    """
    resp1 = await client.post(
        "/api/v1/auth/login",
        json={"phone": test_phone_user.phone},
    )
    assert resp1.status_code == 200

    resp2 = await client.post(
        "/api/v1/auth/login",
        json={"phone": test_phone_user.phone},
    )
    assert resp2.status_code == 200


# ===========================================================================
# POST /api/v1/auth/verify-phone
# ===========================================================================


async def test_verify_phone_success(
    client: AsyncClient,
    test_phone_user: User,
) -> None:
    """Verify with correct code — returns user + sets cookies."""
    # Send code
    await client.post(
        "/api/v1/auth/login",
        json={"phone": test_phone_user.phone},
    )

    resp = await client.post(
        "/api/v1/auth/verify-phone",
        json={"phone": test_phone_user.phone, "code": _CODE},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["message"] == "Телефон успешно подтверждён"
    assert data["user"]["phone"] == test_phone_user.phone
    assert "accessToken" in resp.cookies
    assert "refreshToken" in resp.cookies


async def test_verify_phone_after_pending_registration_returns_permissions(
    client: AsyncClient,
) -> None:
    phone = "+76660004570"
    register_resp = await client.post(
        "/api/v1/auth/register",
        json={"phone": phone, "name": "Pending User", "companies": [_COMPANY]},
    )
    assert register_resp.status_code == 201

    resp = await client.post(
        "/api/v1/auth/verify-phone",
        json={"phone": phone, "code": _CODE},
    )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["user"]["sub_role"] == "administrator"
    assert data["user"]["can_view_applications"] is True
    assert data["user"]["can_create_applications"] is True


async def test_verify_phone_wrong_code(
    client: AsyncClient,
    test_phone_user: User,
) -> None:
    """Wrong code — 400."""
    await client.post(
        "/api/v1/auth/login",
        json={"phone": test_phone_user.phone},
    )
    resp = await client.post(
        "/api/v1/auth/verify-phone",
        json={"phone": test_phone_user.phone, "code": "9999"},
    )
    assert resp.status_code == 400


async def test_verify_phone_no_code_sent(client: AsyncClient) -> None:
    """Verify without prior login — fails."""
    resp = await client.post(
        "/api/v1/auth/verify-phone",
        json={"phone": _NEW_PHONE, "code": _CODE},
    )
    assert resp.status_code == 400


async def test_verify_phone_invalid_format(client: AsyncClient) -> None:
    """Code must be 4 digits."""
    resp = await client.post(
        "/api/v1/auth/verify-phone",
        json={"phone": _NEW_PHONE, "code": "12"},
    )
    assert resp.status_code == 422


# ===========================================================================
# POST /api/v1/auth/resend-code
# ===========================================================================


async def test_resend_code_existing_user(
    client: AsyncClient,
    test_phone_user: User,
) -> None:
    """Resend code for existing user with test phone — 200."""
    resp = await client.post(
        "/api/v1/auth/resend-code",
        json={"phone": test_phone_user.phone},
    )
    assert resp.status_code == 200
    assert resp.json()["message"] == "Новый код подтверждения отправлен"


async def test_resend_code_unknown_user(client: AsyncClient) -> None:
    """Resend code for unknown phone — 404."""
    resp = await client.post(
        "/api/v1/auth/resend-code",
        json={"phone": _NEW_PHONE},
    )
    assert resp.status_code == 404


# ===========================================================================
# POST /api/v1/auth/refresh
# ===========================================================================


async def test_refresh_tokens(
    client: AsyncClient,
    db_session: AsyncSession,
    test_phone_user: User,
) -> None:
    """Refresh with valid refresh token — new tokens in cookies."""
    refresh = await _issue_refresh_token(db_session, test_phone_user.id)
    client.cookies.set("refreshToken", refresh)

    resp = await client.post("/api/v1/auth/refresh")
    assert resp.status_code == 200
    assert resp.json()["message"] == "Токены обновлены"
    assert "accessToken" in resp.cookies
    assert "refreshToken" in resp.cookies


async def test_refresh_uses_settings_for_cookie_policy(
    client: AsyncClient,
    db_session: AsyncSession,
    test_phone_user: User,
) -> None:
    refresh = await _issue_refresh_token(db_session, test_phone_user.id)
    client.cookies.set("refreshToken", refresh)

    old_access_expiry = settings.access_token_expiry_minutes
    old_refresh_expiry = settings.refresh_token_expiry_days
    old_cookie_secure = settings.cookie_secure
    old_cookie_samesite = settings.cookie_samesite
    settings.access_token_expiry_minutes = 5
    settings.refresh_token_expiry_days = 3
    settings.cookie_secure = True
    settings.cookie_samesite = "none"

    try:
        resp = await client.post("/api/v1/auth/refresh")
    finally:
        settings.access_token_expiry_minutes = old_access_expiry
        settings.refresh_token_expiry_days = old_refresh_expiry
        settings.cookie_secure = old_cookie_secure
        settings.cookie_samesite = old_cookie_samesite

    assert resp.status_code == 200
    set_cookie_headers = resp.headers.get_list("set-cookie")
    assert any("accessToken=" in header and "Max-Age=300" in header for header in set_cookie_headers)
    assert any("refreshToken=" in header and "Max-Age=259200" in header for header in set_cookie_headers)
    assert all("Secure" in header for header in set_cookie_headers)
    assert all("SameSite=none" in header for header in set_cookie_headers)


async def test_refresh_no_token(client: AsyncClient) -> None:
    """Refresh without cookie — 401."""
    resp = await client.post("/api/v1/auth/refresh")
    assert resp.status_code == 401


async def test_refresh_invalid_token(client: AsyncClient) -> None:
    """Refresh with garbage token — 401."""
    client.cookies.set("refreshToken", "invalid.token.here")
    resp = await client.post("/api/v1/auth/refresh")
    assert resp.status_code == 401


# ===========================================================================
# GET /api/v1/auth/me
# ===========================================================================


async def test_me_authenticated(
    client: AsyncClient,
    test_phone_token: str,
    test_phone_user: User,
) -> None:
    """GET /me with valid token — returns user info."""
    resp = await client.get("/api/v1/auth/me", headers=_auth(test_phone_token))
    assert resp.status_code == 200
    user = resp.json()["user"]
    assert user["id"] == str(test_phone_user.id)
    assert user["role"] == "client"
    assert user["scopes"] == roles_to_scopes("client")
    assert "scopes" in UserOut.model_json_schema()["properties"]


async def test_access_token_merges_new_role_scopes_into_legacy_claim(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = uuid4()
    payload = {
        "userId": str(user_id),
        "role": "carcraft_employee",
        "scopes": ["auth:admin"],
        "jti": "legacy-scope-token",
    }

    monkeypatch.setattr(
        authentication_service,
        "_decode_access_payload",
        lambda _token: payload,
    )

    async def not_revoked(_jti: str | None) -> bool:
        return False

    monkeypatch.setattr(authentication_service, "is_revoked", not_revoked)

    user = await authentication_service.authenticate_access_token("signed-token")

    assert user["id"] == user_id
    assert user["scopes"] == roles_to_scopes("carcraft_employee")


async def test_access_token_normalizes_company_id_claim_to_uuid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = uuid4()
    company_id = uuid4()
    monkeypatch.setattr(
        authentication_service,
        "_decode_access_payload",
        lambda _token: {
            "userId": str(user_id),
            "role": "distributor",
            "company_id": str(company_id),
            "jti": "company-id-uuid",
        },
    )

    async def not_revoked(_jti: str | None) -> bool:
        return False

    monkeypatch.setattr(authentication_service, "is_revoked", not_revoked)

    user = await authentication_service.authenticate_access_token("signed-token")

    assert user["id"] == user_id
    assert user["company_id"] == company_id
    assert isinstance(user["company_id"], UUID)


async def test_access_token_rejects_invalid_company_id_claim(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        authentication_service,
        "_decode_access_payload",
        lambda _token: {
            "userId": str(uuid4()),
            "role": "distributor",
            "company_id": "not-a-uuid",
            "jti": "invalid-company-id",
        },
    )

    async def not_revoked(_jti: str | None) -> bool:
        return False

    monkeypatch.setattr(authentication_service, "is_revoked", not_revoked)

    with pytest.raises(ServiceError, match="Недействительный токен") as exc_info:
        await authentication_service.authenticate_access_token("signed-token")

    assert exc_info.value.status_code == 401


async def test_access_token_rejects_non_string_company_id_claim(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        authentication_service,
        "_decode_access_payload",
        lambda _token: {
            "userId": str(uuid4()),
            "role": "distributor",
            "company_id": [],
            "jti": "non-string-company-id",
        },
    )

    async def not_revoked(_jti: str | None) -> bool:
        return False

    monkeypatch.setattr(authentication_service, "is_revoked", not_revoked)

    with pytest.raises(ServiceError, match="Недействительный токен") as exc_info:
        await authentication_service.authenticate_access_token("signed-token")

    assert exc_info.value.status_code == 401


async def test_me_no_auth(client: AsyncClient) -> None:
    """GET /me without token — 401."""
    resp = await client.get("/api/v1/auth/me")
    assert resp.status_code == 401


async def test_me_invalid_token(client: AsyncClient) -> None:
    """GET /me with invalid token — 401."""
    resp = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer garbage"},
    )
    assert resp.status_code == 401


# ===========================================================================
# POST /api/v1/auth/logout
# ===========================================================================


async def test_logout(client: AsyncClient) -> None:
    """Logout clears auth cookies."""
    resp = await client.post("/api/v1/auth/logout")
    assert resp.status_code == 200
    assert resp.json()["message"] == "Выход выполнен успешно"


async def test_logout_deletes_uuid_refresh_session(
    client: AsyncClient,
    client_user: User,
    db_session: AsyncSession,
) -> None:
    refresh = await _issue_refresh_token(db_session, client_user.id)
    session_id = UUID(decode_refresh_token(refresh)["sid"])
    assert await auth_repo.get_user_session(db_session, session_id) is not None

    resp = await client.post(
        "/api/v1/auth/logout",
        cookies={"refreshToken": refresh},
    )

    assert resp.status_code == 200
    assert await auth_repo.get_user_session(db_session, session_id) is None


async def test_logout_revokes_access_token(
    client: AsyncClient,
    client_user: User,
) -> None:
    """After logout the access token's jti is on the denylist → /me returns 401."""
    access, _ = generate_tokens(client_user.id, "client", None)

    # Baseline: token works
    ok = await client.get("/api/v1/auth/me", headers=_auth(access))
    assert ok.status_code == 200

    # Logout with the access cookie → revocation
    resp = await client.post(
        "/api/v1/auth/logout",
        cookies={"accessToken": access},
    )
    assert resp.status_code == 200

    # Same access token is now rejected with TOKEN_REVOKED
    revoked = await client.get("/api/v1/auth/me", headers=_auth(access))
    assert revoked.status_code == 401
    detail = revoked.json()
    assert detail["code"] == "TOKEN_REVOKED"


async def test_refresh_revokes_old_access_token(
    client: AsyncClient,
    client_user: User,
    db_session: AsyncSession,
) -> None:
    """Refresh rotates the access token and revokes the previous one."""
    refresh = await _issue_refresh_token(db_session, client_user.id)
    old_access, _ = generate_tokens(client_user.id, "client", None)

    resp = await client.post(
        "/api/v1/auth/refresh",
        cookies={"refreshToken": refresh, "accessToken": old_access},
    )
    assert resp.status_code == 200

    # Old access token is now denylisted
    revoked = await client.get("/api/v1/auth/me", headers=_auth(old_access))
    assert revoked.status_code == 401
    assert revoked.json()["code"] == "TOKEN_REVOKED"


# ===========================================================================
# A3 — phone lockout after N failed OTP attempts
# ===========================================================================


async def test_phone_lockout_after_n_failures(
    client: AsyncClient,
    test_phone_user: User,
) -> None:
    """After max_failures wrong codes, /verify-phone returns 429 PHONE_LOCKED."""
    from infrastructure.settings import settings

    phone = test_phone_user.phone

    # Need a fresh code row so the phone is a valid verify target.
    await client.post("/api/v1/auth/login", json={"phone": phone})

    # Burn through the failure budget with wrong codes
    for _ in range(settings.otp_max_failures):
        bad = await client.post(
            "/api/v1/auth/verify-phone",
            json={"phone": phone, "code": "9999"},
        )
        assert bad.status_code == 400  # InvalidVerificationCodeError

    # Next attempt, even with the correct code, must be locked out
    locked = await client.post(
        "/api/v1/auth/verify-phone",
        json={"phone": phone, "code": _CODE},
    )
    assert locked.status_code == 429


# ===========================================================================
# A4 — refresh-token reuse kills all sessions
# ===========================================================================


async def test_refresh_reuse_kills_all_sessions(
    client: AsyncClient,
    client_user: User,
    db_session: AsyncSession,
) -> None:
    """Presenting a stale refresh token after rotation wipes every session."""
    refresh1 = await _issue_refresh_token(db_session, client_user.id)
    # Issue a second independent session for the same user.
    refresh2 = await _issue_refresh_token(db_session, client_user.id)

    # Rotate session #1 — now refresh1 is stale (hash in DB changed).
    ok = await client.post(
        "/api/v1/auth/refresh",
        cookies={"refreshToken": refresh1},
    )
    assert ok.status_code == 200

    # Reusing the old refresh1 → reuse detected → ALL sessions wiped.
    reuse = await client.post(
        "/api/v1/auth/refresh",
        cookies={"refreshToken": refresh1},
    )
    assert reuse.status_code == 401

    # Session #2 (refresh2) was also nuked as a side-effect.
    also_dead = await client.post(
        "/api/v1/auth/refresh",
        cookies={"refreshToken": refresh2},
    )
    assert also_dead.status_code == 401


# ===========================================================================
# A5 — revoke-all sessions endpoint
# ===========================================================================


async def test_revoke_all_sessions(
    client: AsyncClient,
    client_user: User,
    db_session: AsyncSession,
) -> None:
    """DELETE /users/me/sessions kills every session + current access token."""
    refresh = await _issue_refresh_token(db_session, client_user.id)
    access, _ = generate_tokens(client_user.id, "client", None)

    resp = await client.delete(
        "/api/v1/users/me/sessions",
        headers=_auth(access),
        cookies={"accessToken": access, "refreshToken": refresh},
    )
    assert resp.status_code == 200

    # Current access token is denylisted
    probe = await client.get("/api/v1/auth/me", headers=_auth(access))
    assert probe.status_code == 401
    assert probe.json()["code"] == "TOKEN_REVOKED"

    # Refresh session is gone
    refresh_dead = await client.post(
        "/api/v1/auth/refresh",
        cookies={"refreshToken": refresh},
    )
    assert refresh_dead.status_code == 401


async def test_revoke_all_requires_auth(client: AsyncClient) -> None:
    """Can't call revoke-all without a valid token."""
    resp = await client.delete("/api/v1/users/me/sessions")
    assert resp.status_code == 401


# ===========================================================================
# F4 — login persists session metadata (ip_address, user_agent)
# ===========================================================================


async def test_verify_phone_persists_session_metadata(
    client: AsyncClient,
    test_phone_user: User,
) -> None:
    """After verify-phone, /auth/sessions surfaces the captured UA + IP."""
    await client.post("/api/v1/auth/login", json={"phone": test_phone_user.phone})
    resp = await client.post(
        "/api/v1/auth/verify-phone",
        json={"phone": test_phone_user.phone, "code": _CODE},
        headers={
            "User-Agent": "pytest-ua/1.0",
            "X-Forwarded-For": "203.0.113.7",
        },
    )
    assert resp.status_code == 200
    access = resp.cookies.get("accessToken")
    assert access

    listed = await client.get(
        "/api/v1/users/me/sessions",
        headers={"Authorization": f"Bearer {access}"},
    )
    assert listed.status_code == 200
    sessions = listed.json()["sessions"]
    assert sessions, "expected at least one session after verify-phone"
    mine = sessions[0]
    assert mine["userAgent"] == "pytest-ua/1.0"
    assert mine["ipAddress"] == "203.0.113.7"


# ===========================================================================
# GET /api/v1/health
# ===========================================================================


async def test_health_check(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "healthy"
