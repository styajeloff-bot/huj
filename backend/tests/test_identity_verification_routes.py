from __future__ import annotations

import io
import logging
from datetime import UTC, date, datetime, timedelta
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from domain.services.identity_verification import IdentityVerificationStarted
from infrastructure.models.users import ClientProfile, User, UserIdentityVerification

pytestmark = pytest.mark.asyncio


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


_MOBILE_ID_WEBHOOK_URL = "/api/v1/notifications/webhook/mobileid"
_MOBILE_ID_FINAL_WEBHOOK_URL = "/api/v1/notifications/webhook/mobileid-final"
_ADMIN_MOBILE_ID_DIAGNOSTICS_URL = (
    "/api/v1/admin/mobile-id/diagnostics/si-authorize"
)


class _DiagnosticsProvider:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def start(
        self,
        *,
        user_id: UUID,
        phone_number: str,
        birthdate: date | None,
        correlation_id: UUID,
        family_name: str | None = None,
        given_name: str | None = None,
        middle_name: str | None = None,
    ) -> IdentityVerificationStarted:
        _ = (family_name, given_name, middle_name)
        self.calls.append(
            {
                "user_id": user_id,
                "phone_number": phone_number,
                "birthdate": birthdate,
                "correlation_id": correlation_id,
            }
        )
        return IdentityVerificationStarted(
            auth_req_id="auth-diagnostics",
            phone_masked="+7 *** *** *097",
            expires_at=datetime.now(UTC) + timedelta(minutes=5),
        )


def _install_diagnostics_provider_override(provider: object) -> None:
    from main import app
    from presentation.routers import identity_verification as router_module

    dependency = getattr(
        router_module, "get_mobile_id_diagnostics_provider", None
    )
    if dependency is not None:
        app.dependency_overrides[dependency] = lambda: provider


async def test_admin_mobile_id_diagnostics_requires_employee(
    client: AsyncClient,
    client_token: str,
) -> None:
    payload = {
        "phone": "+79529885097",
        "family_name": "Даурова",
        "given_name": "Алена",
        "middle_name": "Леонтьевна",
        "birth_date": "1990-01-02",
    }

    anonymous = await client.post(_ADMIN_MOBILE_ID_DIAGNOSTICS_URL, json=payload)
    assert anonymous.status_code == 401

    forbidden = await client.post(
        _ADMIN_MOBILE_ID_DIAGNOSTICS_URL,
        headers=_auth(client_token),
        json=payload,
    )
    assert forbidden.status_code == 403


async def test_admin_mobile_id_diagnostics_starts_provider_without_persisting_state(
    client: AsyncClient,
    db_session: AsyncSession,
    employee_user: User,
    employee_token: str,
) -> None:
    provider = _DiagnosticsProvider()
    _install_diagnostics_provider_override(provider)

    response = await client.post(
        _ADMIN_MOBILE_ID_DIAGNOSTICS_URL,
        headers=_auth(employee_token),
        json={
            "phone": "+7 (952) 988-50-97",
            "family_name": " Даурова ",
            "given_name": " Алена ",
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert UUID(body["correlation_id"])
    assert body["status"] == "sms_requested"
    assert body["phone_masked"] == "+7 *** *** *097"
    assert body["provider"] == "mobile_id"
    assert body["expires_at"]
    assert "normalized_request" not in body

    assert provider.calls == [
        {
            "user_id": employee_user.id,
            "phone_number": "+79529885097",
            "birthdate": None,
            "correlation_id": UUID(body["correlation_id"]),
        }
    ]
    verification_count = await db_session.scalar(
        select(func.count(UserIdentityVerification.id))
    )
    profile_count = await db_session.scalar(select(func.count(ClientProfile.id)))
    assert verification_count == 0
    assert profile_count == 0


async def test_admin_mobile_id_diagnostics_rejects_raw_bearer_employee_token(
    employee_token: str,
) -> None:
    from main import app

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as raw_client:
        response = await raw_client.post(
            _ADMIN_MOBILE_ID_DIAGNOSTICS_URL,
            headers={"Authorization": f"Bearer {employee_token}"},
            json={
                "phone": "+79529885097",
                "family_name": "Даурова",
                "given_name": "Алена",
                "middle_name": "Леонтьевна",
            },
    )

    assert response.status_code == 401, response.text
    assert "Bearer auth доступен только для внешних интеграций" in str(
        response.json()["detail"]
    )


async def test_admin_mobile_id_diagnostics_rate_limits_employee_requests(
    client: AsyncClient,
    employee_token: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from infrastructure.settings import settings

    monkeypatch.setattr(settings, "mobile_id_diagnostics_rate_limit_per_window", 3)
    monkeypatch.setattr(settings, "mobile_id_diagnostics_rate_limit_window_seconds", 600)
    provider = _DiagnosticsProvider()
    _install_diagnostics_provider_override(provider)
    payload = {
        "phone": "+79529885097",
        "family_name": "Даурова",
        "given_name": "Алена",
    }

    for _ in range(3):
        response = await client.post(
            _ADMIN_MOBILE_ID_DIAGNOSTICS_URL,
            headers=_auth(employee_token),
            json=payload,
        )
        assert response.status_code == 200, response.text

    limited = await client.post(
        _ADMIN_MOBILE_ID_DIAGNOSTICS_URL,
        headers=_auth(employee_token),
        json=payload,
    )

    assert limited.status_code == 429, limited.text
    assert limited.json()["detail"] == (
        "Слишком много диагностических запросов Mobile ID. Попробуйте позже."
    )
    assert len(provider.calls) == 3


async def test_admin_mobile_id_diagnostics_maps_provider_error(
    client: AsyncClient,
    employee_token: str,
) -> None:
    from infrastructure.services.mobile_id.client import (
        MobileIdProviderUnavailableError,
    )

    class ErrorProvider:
        async def start(self, **kwargs: object) -> IdentityVerificationStarted:
            _ = kwargs
            raise MobileIdProviderUnavailableError(
                "Mobile ID отклонил запрос верификации.",
                status_code=502,
            )

    _install_diagnostics_provider_override(ErrorProvider())

    response = await client.post(
        _ADMIN_MOBILE_ID_DIAGNOSTICS_URL,
        headers=_auth(employee_token),
        json={
            "phone": "+79529885097",
            "family_name": "Даурова",
            "given_name": "Алена",
            "middle_name": "Леонтьевна",
        },
    )

    assert response.status_code == 502, response.text
    assert response.json()["detail"] == "Mobile ID отклонил запрос верификации."


async def test_identity_verification_routes_require_auth(
    client: AsyncClient,
) -> None:
    status = await client.get("/api/v1/users/me/identity-verification")
    assert status.status_code == 401

    started = await client.post("/api/v1/users/me/identity-verifications", json={})
    assert started.status_code == 401


async def test_identity_verification_route_happy_path(
    client: AsyncClient,
    db_session: AsyncSession,
    client_user: User,
    client_token: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from infrastructure.settings import settings

    monkeypatch.setattr(settings, "mobile_id_enabled", False)
    db_session.add(ClientProfile(user_id=client_user.id, birth_date=date(1990, 1, 2)))
    await db_session.flush()

    start = await client.post(
        "/api/v1/users/me/identity-verifications",
        headers=_auth(client_token),
        json={},
    )
    assert start.status_code == 201, start.text
    body = start.json()
    assert body["status"] == "sms_requested"
    assert body["verification_id"]
    assert body["phone_masked"]
    assert start.headers["location"].endswith(body["verification_id"])

    sms = await client.post(
        f"/api/v1/users/me/identity-verifications/{body['verification_id']}/sms-code",
        headers=_auth(client_token),
        json={"code": "0000"},
    )
    assert sms.status_code == 200, sms.text
    assert sms.json()["status"] == "verified"

    status = await client.get(
        "/api/v1/users/me/identity-verification",
        headers=_auth(client_token),
    )
    assert status.status_code == 200, status.text
    assert status.json()["verified"] is True


async def test_identity_verification_sms_code_provider_error_returns_message(
    client: AsyncClient,
    db_session: AsyncSession,
    client_user: User,
    client_token: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from infrastructure.settings import settings

    monkeypatch.setattr(settings, "mobile_id_enabled", False)
    db_session.add(ClientProfile(user_id=client_user.id, birth_date=date(1990, 1, 2)))
    await db_session.flush()

    start = await client.post(
        "/api/v1/users/me/identity-verifications",
        headers=_auth(client_token),
        json={},
    )
    assert start.status_code == 201, start.text

    sms = await client.post(
        f"/api/v1/users/me/identity-verifications/{start.json()['verification_id']}/sms-code",
        headers=_auth(client_token),
        json={"code": "9999"},
    )

    assert sms.status_code == 422, sms.text
    assert sms.json()["detail"] == (
        "Неверный код подтверждения. Проверьте SMS и попробуйте ещё раз."
    )


async def test_public_mobile_id_callbacks_are_idempotent(
    client: AsyncClient,
    db_session: AsyncSession,
    client_user: User,
    client_token: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from infrastructure.settings import settings

    monkeypatch.setattr(settings, "mobile_id_enabled", False)
    db_session.add(ClientProfile(user_id=client_user.id, birth_date=date(1990, 1, 2)))
    await db_session.flush()
    start = await client.post(
        "/api/v1/users/me/identity-verifications",
        headers=_auth(client_token),
        json={},
    )
    assert start.status_code == 201, start.text
    correlation_id = start.json()["correlation_id"]

    payload = {
        "correlation_id": correlation_id,
        "auth_req_id": "auth-route",
        "smsotp_endpoint": "https://mts.example/sms",
        "send": {"verify_code": "enter_otp_code"},
        "leading_kyc_match": True,
    }
    first = await client.post(_MOBILE_ID_WEBHOOK_URL, json=payload)
    second = await client.post(_MOBILE_ID_WEBHOOK_URL, json=payload)
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.json()["id"] == second.json()["id"]


async def test_public_mobile_id_sms_webhook_accepts_sms_otp_notification(
    client: AsyncClient,
    db_session: AsyncSession,
    client_user: User,
    client_token: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from infrastructure.settings import settings

    monkeypatch.setattr(settings, "mobile_id_enabled", False)
    db_session.add(ClientProfile(user_id=client_user.id, birth_date=date(1990, 1, 2)))
    await db_session.flush()
    start = await client.post(
        "/api/v1/users/me/identity-verifications",
        headers=_auth(client_token),
        json={},
    )
    assert start.status_code == 201, start.text

    response = await client.post(
        _MOBILE_ID_WEBHOOK_URL,
        json={
            "correlation_id": start.json()["correlation_id"],
            "auth_req_id": "auth-route",
            "smsotp_endpoint": "https://mts.example/sms",
            "send": {"verify_code": "enter_otp_code"},
            "leading_kyc_match": True,
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["id"]
    assert response.json()["status"] == "sms_requested"


async def test_public_mobile_id_final_webhook_accepts_final_notification(
    client: AsyncClient,
    db_session: AsyncSession,
    client_user: User,
    client_token: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from infrastructure.settings import settings

    monkeypatch.setattr(settings, "mobile_id_enabled", False)
    monkeypatch.setattr(settings, "mobile_id_verbose_logs", True)
    db_session.add(ClientProfile(user_id=client_user.id, birth_date=date(1990, 1, 2)))
    await db_session.flush()
    start = await client.post(
        "/api/v1/users/me/identity-verifications",
        headers=_auth(client_token),
        json={},
    )
    assert start.status_code == 201, start.text

    log_stream = io.StringIO()
    log_handler = logging.StreamHandler(log_stream)
    log_handler.setLevel(logging.INFO)
    mts_logger = logging.getLogger("carcraft-backend")
    previous_level = mts_logger.level
    mts_logger.setLevel(logging.INFO)
    mts_logger.addHandler(log_handler)

    try:
        response = await client.post(
            _MOBILE_ID_FINAL_WEBHOOK_URL,
            json={
                "correlation_id": start.json()["correlation_id"],
                "id_token": "id-token-final",
                "access_token": "access-token-final",
                "jwks_uri": "https://mts.example/jwks",
                "leading_kyc_match": True,
            },
        )
    finally:
        mts_logger.removeHandler(log_handler)
        mts_logger.setLevel(previous_level)

    assert response.status_code == 200, response.text
    assert response.json()["id"]
    assert response.json()["status"] == "verified"
    log_text = log_stream.getvalue()
    assert "path=/api/v1/notifications/webhook/mobileid-final" in log_text
    assert "jwks_uri=https://mts.example/jwks" in log_text
    assert "jwks_uri_host=mts.example" in log_text
    assert "payload={'correlation_id':" in log_text
    assert "id-token-final" not in log_text
    assert "access-token-final" not in log_text
    assert "'id_token': '***'" in log_text
    assert "'access_token': '***'" in log_text

    status = await client.get(
        "/api/v1/users/me/identity-verification",
        headers=_auth(client_token),
    )
    assert status.status_code == 200, status.text
    assert status.json()["verified"] is True


async def test_public_mobile_id_sms_webhook_ignores_final_notification_payload(
    client: AsyncClient,
) -> None:
    response = await client.post(
        _MOBILE_ID_WEBHOOK_URL,
        json={
            "correlation_id": "00000000-0000-0000-0000-000000021502",
            "id_token": "id-token",
            "access_token": "access-token",
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "ignored"


async def test_public_mobile_id_final_webhook_redacts_invalid_tokens(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from infrastructure.settings import settings

    monkeypatch.setattr(settings, "mobile_id_verbose_logs", True)
    log_stream = io.StringIO()
    log_handler = logging.StreamHandler(log_stream)
    log_handler.setLevel(logging.INFO)
    mts_logger = logging.getLogger("carcraft-backend")
    previous_level = mts_logger.level
    mts_logger.setLevel(logging.INFO)
    mts_logger.addHandler(log_handler)

    try:
        response = await client.post(
            _MOBILE_ID_FINAL_WEBHOOK_URL,
            json={
                "correlation_id": "00000000-0000-0000-0000-000000021502",
                "id_token": ["secret-invalid-id-token"],
                "access_token": {"token": "secret-invalid-access-token"},
            },
        )
    finally:
        mts_logger.removeHandler(log_handler)
        mts_logger.setLevel(previous_level)

    assert response.status_code == 200, response.text
    assert response.json() == {
        "id": None,
        "status": "ignored",
        "detail": "Invalid Mobile ID callback payload",
    }
    log_text = log_stream.getvalue()
    assert "reason=validation_error" in log_text
    assert "secret-invalid-id-token" not in log_text
    assert "secret-invalid-access-token" not in log_text
    assert "'id_token': '***'" in log_text
    assert "'access_token': '***'" in log_text


async def test_public_mobile_id_final_webhook_ignores_sms_otp_payload(
    client: AsyncClient,
) -> None:
    response = await client.post(
        _MOBILE_ID_FINAL_WEBHOOK_URL,
        json={
            "correlation_id": "00000000-0000-0000-0000-000000021502",
            "auth_req_id": "auth-route",
            "smsotp_endpoint": "https://mts.example/sms",
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "ignored"


async def test_public_mobile_id_sms_webhook_logs_sms_otp_callback(
    client: AsyncClient,
    db_session: AsyncSession,
    client_user: User,
    client_token: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from infrastructure.settings import settings

    monkeypatch.setattr(settings, "mobile_id_enabled", False)
    monkeypatch.setattr(settings, "mobile_id_verbose_logs", True)
    db_session.add(ClientProfile(user_id=client_user.id, birth_date=date(1990, 1, 2)))
    await db_session.flush()
    start = await client.post(
        "/api/v1/users/me/identity-verifications",
        headers=_auth(client_token),
        json={},
    )
    assert start.status_code == 201, start.text
    correlation_id = start.json()["correlation_id"]
    log_stream = io.StringIO()
    log_handler = logging.StreamHandler(log_stream)
    log_handler.setLevel(logging.INFO)
    mts_logger = logging.getLogger("carcraft-backend")
    previous_level = mts_logger.level
    mts_logger.setLevel(logging.INFO)
    mts_logger.addHandler(log_handler)

    try:
        response = await client.post(
            _MOBILE_ID_WEBHOOK_URL,
            json={
                "correlation_id": correlation_id,
                "auth_req_id": "auth-route",
                "smsotp_endpoint": "https://mts.example/sms",
                "send": {"verify_code": "enter_otp_code"},
                "leading_kyc_match": True,
            },
        )
    finally:
        mts_logger.removeHandler(log_handler)
        mts_logger.setLevel(previous_level)

    assert response.status_code == 200, response.text
    log_text = log_stream.getvalue()
    assert "[ MTS ] callback received operation=mobile_id_webhook" in log_text
    assert "path=/api/v1/notifications/webhook/mobileid" in log_text
    assert "payload_type=sms_otp" in log_text
    assert f"correlation_id={correlation_id}" in log_text
    assert "payload={'correlation_id':" in log_text
    assert "enter_otp_code" not in log_text
    assert "'verify_code': '***'" in log_text
    assert "[ MTS ] callback processed operation=mobile_id_webhook" in log_text
    assert "status=sms_requested" in log_text


async def test_public_mobile_id_callback_with_invalid_bearer_is_ignored(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from infrastructure.settings import settings

    monkeypatch.setattr(settings, "mobile_id_notification_token", "expected-token")
    response = await client.post(
        _MOBILE_ID_WEBHOOK_URL,
        headers={"Authorization": "Bearer wrong-token"},
        json={
            "correlation_id": "00000000-0000-0000-0000-000000021502",
            "auth_req_id": "auth-missing",
            "smsotp_endpoint": "https://mts.example/sms",
            "send": {"verify_code": "enter_otp_code"},
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "ignored"


async def test_public_mobile_id_callback_unknown_correlation_is_200(
    client: AsyncClient,
) -> None:
    response = await client.post(
        _MOBILE_ID_WEBHOOK_URL,
        json={
            "correlation_id": "00000000-0000-0000-0000-000000021502",
            "auth_req_id": "auth-missing",
            "smsotp_endpoint": "https://mts.example/sms",
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "ignored"


async def test_public_mobile_id_final_webhook_logs_provider_error_payload(
    client: AsyncClient,
) -> None:
    correlation_id = "00000000-0000-0000-0000-000000021502"
    log_stream = io.StringIO()
    log_handler = logging.StreamHandler(log_stream)
    log_handler.setLevel(logging.INFO)
    mts_logger = logging.getLogger("carcraft-backend")
    previous_level = mts_logger.level
    mts_logger.setLevel(logging.INFO)
    mts_logger.addHandler(log_handler)

    try:
        response = await client.post(
            _MOBILE_ID_FINAL_WEBHOOK_URL,
            json={
                "correlation_id": correlation_id,
                "auth_req_id": "auth-route",
                "error": "access_denied",
                "error_description": "User declined Mobile ID request",
            },
        )
    finally:
        mts_logger.removeHandler(log_handler)
        mts_logger.setLevel(previous_level)

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "ignored"
    log_text = log_stream.getvalue()
    assert "payload_type=error" in log_text
    assert "payload={'correlation_id':" in log_text
    assert "access_denied" in log_text
    assert "User declined Mobile ID request" in log_text
    assert "payload_keys" not in log_text


async def test_mobile_id_legacy_callback_routes_are_not_registered(
    client: AsyncClient,
) -> None:
    sms_response = await client.post(
        "/api/v1/mobile-id/sms-otp-notification",
        json={
            "correlation_id": "00000000-0000-0000-0000-000000021502",
            "auth_req_id": "auth-missing",
            "smsotp_endpoint": "https://mts.example/sms",
        },
    )
    notification_response = await client.post(
        "/api/v1/mobile-id/notification",
        json={
            "correlation_id": "00000000-0000-0000-0000-000000021502",
            "id_token": "id-token",
            "access_token": "access-token",
        },
    )

    assert sms_response.status_code == 404
    assert notification_response.status_code == 404


async def test_identity_verification_sms_code_validation(
    client: AsyncClient,
    client_token: str,
) -> None:
    response = await client.post(
        "/api/v1/users/me/identity-verifications/not-a-uuid/sms-code",
        headers=_auth(client_token),
        json={"code": "12"},
    )
    assert response.status_code == 422
