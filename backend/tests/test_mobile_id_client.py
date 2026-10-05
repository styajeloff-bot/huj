from __future__ import annotations

import base64
import io
import json
import logging
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey
from jose import jwe, jwt

from infrastructure.services.mobile_id.client import (
    LocalMobileIdProvider,
    MobileIdHttpProvider,
    MobileIdProviderPendingError,
    MobileIdProviderUnavailableError,
    get_mobile_id_provider,
)
from infrastructure.settings import Settings, settings

pytestmark = pytest.mark.asyncio

_MOBILE_ID_PUBLIC_ORIGIN = "https://test.multileasing.ru"
_MOBILE_ID_FINAL_WEBHOOK_URI = (
    "https://test.multileasing.ru/api/v1/notifications/webhook/mobileid-final"
)
_MOBILE_ID_WEBHOOK_URI = (
    "https://test.multileasing.ru/api/v1/notifications/webhook/mobileid"
)
_MOBILE_ID_JWKS_URI = "https://test.multileasing.ru/.well-known/jwks.json"
_MOBILE_ID_BASIC_SCOPE = "openid mc_authn mc_identity_basic"


def _b64url_int(value: int) -> str:
    raw = value.to_bytes((value.bit_length() + 7) // 8, "big")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _public_jwk(
    private_key: RSAPrivateKey,
    kid: str,
    use: str,
    alg: str,
) -> dict[str, str]:
    numbers = private_key.public_key().public_numbers()
    return {
        "kty": "RSA",
        "use": use,
        "alg": alg,
        "kid": kid,
        "n": _b64url_int(numbers.n),
        "e": _b64url_int(numbers.e),
    }


def _private_key_pem(private_key: RSAPrivateKey) -> bytes:
    return private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )


def _write_private_key(tmp_path: Path, kid: str) -> RSAPrivateKey:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    (tmp_path / f"{kid}.pem").write_bytes(_private_key_pem(private_key))
    (tmp_path / f"{kid}.pub.pem").write_bytes(
        private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    if kid != "enc" and not (tmp_path / "enc.pem").exists():
        _write_private_key(tmp_path, "enc")
    return private_key


def _capture_mobile_id_logs() -> tuple[logging.Logger, io.StringIO, logging.Handler, int]:
    log_stream = io.StringIO()
    handler = logging.StreamHandler(log_stream)
    handler.setLevel(logging.INFO)
    mts_logger = logging.getLogger("carcraft-backend")
    previous_level = mts_logger.level
    mts_logger.setLevel(logging.INFO)
    mts_logger.addHandler(handler)
    return mts_logger, log_stream, handler, previous_level


def _assert_verbose_kyc_request_diagnostics(
    request_bodies: list[bytes],
    log_text: str,
) -> None:
    assert len(request_bodies) == 1
    request_body = request_bodies[0]
    assert request_body.count(b".") == 4
    assert b"1990-01-01" not in request_body
    assert "Иванов".encode() not in request_body
    request_log = next(
        line
        for line in log_text.splitlines()
        if "[ MTS ] request operation=kyc_match_split" in line
    )
    assert "'birthdate': '1990-01-01'" in request_log
    assert "'family_name': 'Иванов'" in request_log
    assert "<content " not in request_log
    assert "access-21502" not in request_log


async def test_disabled_mobile_id_uses_local_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "mobile_id_enabled", False)

    provider = get_mobile_id_provider()

    assert isinstance(provider, LocalMobileIdProvider)
    started = await provider.start(
        user_id=uuid4(),
        phone_number="+76662150231",
        birthdate=date(1990, 1, 1),
        correlation_id=uuid4(),
    )
    assert started.auth_req_id.startswith("local-")

    verified = await provider.submit_sms_code(
        auth_req_id=started.auth_req_id,
        smsotp_endpoint=None,
        code="0000",
        phone_number="+76662150231",
        birthdate=date(1990, 1, 1),
    )
    assert verified.birthdate_match == "Y"


async def test_enabled_mobile_id_provider_starts_si_authorize(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_private_key(tmp_path, "sig")
    monkeypatch.setattr(settings, "jwt_keys_dir", str(tmp_path))
    monkeypatch.setattr(settings, "mobile_id_sig_kid", "sig")
    monkeypatch.setattr(settings, "mobile_id_client_id", "mts_test_service")
    monkeypatch.setattr(settings, "mobile_id_notification_token", "notify-token")
    monkeypatch.setattr(settings, "api_url", "https://test.multileasing.ru")

    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "auth_req_id": "auth-21502",
                "expires_in": 140,
                "correlation_id": "ignored",
            },
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://idgw.mobileid.mts.ru",
    ) as client:
        provider = MobileIdHttpProvider(http_client=client)
        started = await provider.start(
            user_id=uuid4(),
            phone_number="+76662150232",
            birthdate=date(1990, 1, 1),
            correlation_id=uuid4(),
        )

    assert started.auth_req_id == "auth-21502"
    assert requests[0].url.path == "/oidc/si-authorize"
    body = json.loads(requests[0].content)
    assert body["client_id"] == "mts_test_service"
    assert body["response_type"] == "mc_si_async_code"
    assert body["scope"] == _MOBILE_ID_BASIC_SCOPE
    request_payload = jwt.get_unverified_claims(body["request"])
    assert request_payload["scope"] == _MOBILE_ID_BASIC_SCOPE
    assert request_payload["version"] == "mc_si_r2_v1.0"
    assert request_payload["client_notification_token"] == "notify-token"
    assert request_payload["notification_uri"] == _MOBILE_ID_FINAL_WEBHOOK_URI
    assert request_payload["sms_otp_notification_uri"] == _MOBILE_ID_WEBHOOK_URI
    assert request_payload["login_hint"] == "MSISDN:76662150232"


async def test_mobile_id_callback_uri_defaults_use_test_public_url(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_private_key(tmp_path, "sig")
    monkeypatch.setattr(settings, "jwt_keys_dir", str(tmp_path))
    monkeypatch.setattr(settings, "mobile_id_sig_kid", "sig")
    monkeypatch.setattr(settings, "mobile_id_client_id", "mts_test_service")
    monkeypatch.setattr(settings, "mobile_id_notification_token", "notify-token")
    monkeypatch.setattr(settings, "api_url", "https://test.multileasing.ru")
    monkeypatch.setattr(settings, "public_url", "")
    monkeypatch.setattr(
        settings,
        "mobile_id_notification_uri",
        Settings.model_fields["mobile_id_notification_uri"].default,
    )
    monkeypatch.setattr(
        settings,
        "mobile_id_sms_otp_notification_uri",
        Settings.model_fields["mobile_id_sms_otp_notification_uri"].default,
    )
    monkeypatch.setattr(
        settings,
        "mobile_id_jwks_public_url",
        Settings.model_fields["mobile_id_jwks_public_url"].default,
    )

    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"auth_req_id": "auth-21502"})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://idgw.mobileid.mts.ru",
    ) as client:
        provider = MobileIdHttpProvider(http_client=client)
        mts_logger, log_stream, log_handler, previous_level = _capture_mobile_id_logs()
        try:
            await provider.start(
                user_id=uuid4(),
                phone_number="+76662150232",
                birthdate=date(1990, 1, 1),
                correlation_id=uuid4(),
            )
        finally:
            mts_logger.removeHandler(log_handler)
            mts_logger.setLevel(previous_level)

    request_payload = jwt.get_unverified_claims(json.loads(requests[0].content)["request"])
    assert request_payload["notification_uri"] == _MOBILE_ID_FINAL_WEBHOOK_URI
    assert request_payload["sms_otp_notification_uri"] == _MOBILE_ID_WEBHOOK_URI
    assert request_payload["jwks_public_url"] == _MOBILE_ID_JWKS_URI
    assert f"'jwks_public_url': '{_MOBILE_ID_JWKS_URI}'" in log_stream.getvalue()


async def test_mobile_id_public_urls_keep_absolute_overrides(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_private_key(tmp_path, "sig")
    monkeypatch.setattr(settings, "jwt_keys_dir", str(tmp_path))
    monkeypatch.setattr(settings, "mobile_id_sig_kid", "sig")
    monkeypatch.setattr(settings, "mobile_id_client_id", "mts_test_service")
    monkeypatch.setattr(settings, "mobile_id_notification_token", "notify-token")
    monkeypatch.setattr(settings, "api_url", "https://test.multileasing.ru")
    monkeypatch.setattr(
        settings,
        "mobile_id_notification_uri",
        "https://callbacks.example.test/mobile-id",
    )
    monkeypatch.setattr(
        settings,
        "mobile_id_sms_otp_notification_uri",
        "https://callbacks.example.test/mobile-id/sms",
    )
    monkeypatch.setattr(
        settings,
        "mobile_id_jwks_public_url",
        "https://keys.example.test/.well-known/jwks.json",
    )

    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"auth_req_id": "auth-21502"})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://idgw.mobileid.mts.ru",
    ) as client:
        provider = MobileIdHttpProvider(http_client=client)
        mts_logger, log_stream, log_handler, previous_level = _capture_mobile_id_logs()
        try:
            await provider.start(
                user_id=uuid4(),
                phone_number="+76662150232",
                birthdate=date(1990, 1, 1),
                correlation_id=uuid4(),
            )
        finally:
            mts_logger.removeHandler(log_handler)
            mts_logger.setLevel(previous_level)

    request_payload = jwt.get_unverified_claims(json.loads(requests[0].content)["request"])
    assert request_payload["notification_uri"] == "https://callbacks.example.test/mobile-id"
    assert (
        request_payload["sms_otp_notification_uri"]
        == "https://callbacks.example.test/mobile-id/sms"
    )
    assert (
        request_payload["jwks_public_url"]
        == "https://keys.example.test/.well-known/jwks.json"
    )
    assert (
        "'jwks_public_url': 'https://keys.example.test/.well-known/jwks.json'"
        in log_stream.getvalue()
    )


async def test_mobile_id_relative_public_urls_use_public_url_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_private_key(tmp_path, "sig")
    monkeypatch.setattr(settings, "jwt_keys_dir", str(tmp_path))
    monkeypatch.setattr(settings, "mobile_id_sig_kid", "sig")
    monkeypatch.setattr(settings, "mobile_id_client_id", "mts_test_service")
    monkeypatch.setattr(settings, "mobile_id_notification_token", "notify-token")
    monkeypatch.setattr(settings, "api_url", "")
    monkeypatch.setattr(settings, "public_url", "https://test.multileasing.ru")
    monkeypatch.setattr(
        settings,
        "mobile_id_notification_uri",
        Settings.model_fields["mobile_id_notification_uri"].default,
    )
    monkeypatch.setattr(
        settings,
        "mobile_id_sms_otp_notification_uri",
        Settings.model_fields["mobile_id_sms_otp_notification_uri"].default,
    )

    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"auth_req_id": "auth-21502"})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://idgw.mobileid.mts.ru",
    ) as client:
        provider = MobileIdHttpProvider(http_client=client)
        await provider.start(
            user_id=uuid4(),
            phone_number="+76662150232",
            birthdate=date(1990, 1, 1),
            correlation_id=uuid4(),
        )

    request_payload = jwt.get_unverified_claims(json.loads(requests[0].content)["request"])
    assert request_payload["notification_uri"] == _MOBILE_ID_FINAL_WEBHOOK_URI
    assert request_payload["sms_otp_notification_uri"] == _MOBILE_ID_WEBHOOK_URI


async def test_mobile_id_relative_public_urls_require_base_url(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_private_key(tmp_path, "sig")
    monkeypatch.setattr(settings, "jwt_keys_dir", str(tmp_path))
    monkeypatch.setattr(settings, "mobile_id_sig_kid", "sig")
    monkeypatch.setattr(settings, "mobile_id_client_id", "mts_test_service")
    monkeypatch.setattr(settings, "mobile_id_notification_token", "notify-token")
    monkeypatch.setattr(settings, "api_url", "")
    monkeypatch.setattr(settings, "public_url", "")
    monkeypatch.setattr(
        settings,
        "mobile_id_notification_uri",
        Settings.model_fields["mobile_id_notification_uri"].default,
    )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json={})),
        base_url="https://idgw.mobileid.mts.ru",
    ) as client:
        provider = MobileIdHttpProvider(http_client=client)
        with pytest.raises(
            RuntimeError,
            match="Mobile ID public URL base is not configured",
        ):
            await provider.start(
                user_id=uuid4(),
                phone_number="+76662150232",
                birthdate=date(1990, 1, 1),
                correlation_id=uuid4(),
            )

async def test_enabled_mobile_id_provider_logs_mts_request_and_response(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_private_key(tmp_path, "sig")
    monkeypatch.setattr(settings, "jwt_keys_dir", str(tmp_path))
    monkeypatch.setattr(settings, "mobile_id_sig_kid", "sig")
    monkeypatch.setattr(settings, "mobile_id_client_id", "mts_test_service")
    monkeypatch.setattr(settings, "mobile_id_notification_token", "notify-token")
    monkeypatch.setattr(settings, "api_url", "https://test.multileasing.ru")
    monkeypatch.setattr(settings, "mobile_id_base_url", "https://idgw.mobileid.mts.ru/oidc")

    captured_request_token = ""

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_request_token
        captured_request_token = json.loads(request.content)["request"]
        return httpx.Response(200, json={"auth_req_id": "auth-log", "expires_in": 140})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://idgw.mobileid.mts.ru",
    ) as client:
        provider = MobileIdHttpProvider(http_client=client)
        mts_logger, log_stream, log_handler, previous_level = _capture_mobile_id_logs()
        try:
            await provider.start(
                user_id=uuid4(),
                phone_number="+76662150232",
                birthdate=date(1990, 1, 1),
                correlation_id=uuid4(),
            )
        finally:
            mts_logger.removeHandler(log_handler)
            mts_logger.setLevel(previous_level)

    log_text = log_stream.getvalue()
    assert "[ MTS ] request_claims operation=si_authorize" in log_text
    assert f"'notification_uri': '{_MOBILE_ID_FINAL_WEBHOOK_URI}'" in log_text
    assert f"'sms_otp_notification_uri': '{_MOBILE_ID_WEBHOOK_URI}'" in log_text
    assert "[ MTS ] request operation=si_authorize" in log_text
    assert "[ MTS ] response operation=si_authorize status_code=200" in log_text
    assert captured_request_token
    assert captured_request_token not in log_text
    assert "'request': '***'" in log_text


async def _mobile_id_response_log(
    monkeypatch: pytest.MonkeyPatch,
    *,
    verbose: bool,
    response: httpx.Response,
    request_headers: dict[str, str] | None = None,
    request_json: dict[str, str] | None = None,
    operation: str = "si_authorize",
) -> str:
    monkeypatch.setattr(settings, "mobile_id_verbose_logs", verbose)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: response),
    ) as client:
        provider = MobileIdHttpProvider(http_client=client)
        mts_logger, log_stream, log_handler, previous_level = _capture_mobile_id_logs()
        try:
            await provider._request(
                "POST",
                "https://idgw.mobileid.mts.ru/oidc/si-authorize",
                mts_operation=operation,
                headers=request_headers or {},
                json=request_json or {},
            )
        finally:
            mts_logger.removeHandler(log_handler)
            mts_logger.setLevel(previous_level)

    return log_stream.getvalue()


async def test_mobile_id_verbose_logs_reveal_si_authorize_plain_text_error_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response_body = "MTS test: could not obtain jwks_url for request 21502"

    logs = await _mobile_id_response_log(
        monkeypatch,
        verbose=True,
        response=httpx.Response(
            500,
            text=response_body,
            headers={"Content-Type": "text/plain"},
        ),
    )

    response_log = next(
        line
        for line in logs.splitlines()
        if "[ MTS ] response operation=si_authorize" in line
    )
    assert response_body in response_log
    assert "<response " not in response_log
    assert "<content " not in response_log


async def test_mobile_id_non_verbose_logs_hide_si_authorize_plain_text_error_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response_body = b"MTS test: could not obtain jwks_url for request 21502"

    logs = await _mobile_id_response_log(
        monkeypatch,
        verbose=False,
        response=httpx.Response(
            500,
            content=response_body,
            headers={"Content-Type": "text/plain"},
        ),
    )

    response_log = next(
        line
        for line in logs.splitlines()
        if "[ MTS ] response operation=si_authorize" in line
    )
    assert response_body.decode("ascii") not in response_log
    assert (
        f"<response {len(response_body)} bytes content_type=text/plain>"
        in response_log
    )


async def test_mobile_id_verbose_logs_redact_credentials_and_jwts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    authorization = "Bearer access-secret-21502"
    signed_request_jwt = (
        "eyJhbGciOiJSUzI1NiIsImtpZCI6InJlcXVlc3Qtc2VjcmV0In0."
        "eyJzdWIiOiJyZXF1ZXN0LXBpaS0yMTUwMiJ9.request-signature-21502"
    )
    response_jwt = (
        "eyJhbGciOiJSUzI1NiIsImtpZCI6InJlc3BvbnNlLXNlY3JldCJ9."
        "eyJzdWIiOiJyZXNwb25zZS1waWktMjE1MDIifQ.response-signature-21502"
    )

    logs = await _mobile_id_response_log(
        monkeypatch,
        verbose=True,
        response=httpx.Response(
            500,
            json={
                "error": "invalid_request",
                "error_description": "safe provider diagnostic 21502",
                "access_token": "response-access-secret-21502",
                "id_token": response_jwt,
                "debug_token": response_jwt,
                "refresh_token": "opaque-refresh-secret-21502",
            },
        ),
        request_headers={"Authorization": authorization},
        request_json={"request": signed_request_jwt},
    )

    assert "safe provider diagnostic 21502" in logs
    assert "'Authorization': '***'" in logs
    assert "'request': '***'" in logs
    assert "'access_token': '***'" in logs
    assert "'id_token': '***'" in logs
    assert authorization not in logs
    assert "response-access-secret-21502" not in logs
    assert signed_request_jwt not in logs
    assert response_jwt not in logs
    assert "opaque-refresh-secret-21502" not in logs


async def test_mobile_id_verbose_text_logs_redact_embedded_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    embedded_jwt = (
        "eyJhbGciOiJSUzI1NiIsImtpZCI6ImVtYmVkZGVkLXNlY3JldCJ9."
        "eyJzdWIiOiJlbWJlZGRlZC1waWktMjE1MDIifQ.embedded-signature-21502"
    )
    embedded_notification_token = "embedded-notification-secret-21502"
    embedded_access_token = "embedded-access-secret-21502"
    embedded_basic_credentials = "Basic embedded-basic-secret-21502"
    embedded_digest_credentials = (
        'Digest username="embedded-user-21502", nonce="embedded-nonce-21502", '
        'response="embedded-digest-response-21502"'
    )
    response_body = (
        "safe MTS diagnostic 21502; "
        f"token={embedded_jwt}; "
        f"client_notification_token={embedded_notification_token}\n"
        f"Authorization: Bearer {embedded_access_token}\n"
        f"authorization={embedded_basic_credentials}\n"
        f"Authorization: {embedded_digest_credentials}"
    )

    logs = await _mobile_id_response_log(
        monkeypatch,
        verbose=True,
        response=httpx.Response(
            500,
            text=response_body,
            headers={"Content-Type": "text/plain; charset=utf-8"},
        ),
    )

    assert "safe MTS diagnostic 21502" in logs
    assert "token=***" in logs
    assert "client_notification_token=***" in logs
    assert "Authorization: ***" in logs
    assert "authorization=***" in logs
    assert embedded_jwt not in logs
    assert embedded_notification_token not in logs
    assert embedded_access_token not in logs
    assert embedded_basic_credentials not in logs
    assert embedded_digest_credentials not in logs
    assert "embedded-user-21502" not in logs
    assert "embedded-nonce-21502" not in logs
    assert "embedded-digest-response-21502" not in logs


async def test_mobile_id_non_verbose_logs_keep_problem_json_hidden(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response_body = b'{"detail":"test-only-provider-diagnostic-21502"}'

    logs = await _mobile_id_response_log(
        monkeypatch,
        verbose=False,
        response=httpx.Response(
            500,
            content=response_body,
            headers={"Content-Type": "application/problem+json"},
        ),
    )

    response_log = next(
        line
        for line in logs.splitlines()
        if "[ MTS ] response operation=si_authorize" in line
    )
    assert response_body.decode("ascii") not in response_log
    assert (
        f"<response {len(response_body)} bytes "
        "content_type=application/problem+json>" in response_log
    )


async def test_mobile_id_verbose_json_logs_include_envelope_and_full_public_jwks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response_payload = {
        "keys": [
            {
                "kid": "mts-public-sig-21502",
                "kty": "RSA",
                "n": "public-modulus-21502",
                "e": "AQAB",
            }
        ]
    }
    response = httpx.Response(200, json=response_payload)

    logs = await _mobile_id_response_log(
        monkeypatch,
        verbose=True,
        response=response,
        operation="fetch_jwks",
    )

    response_log = next(
        line
        for line in logs.splitlines()
        if "[ MTS ] response operation=fetch_jwks" in line
    )
    assert "'content_type': 'application/json'" in response_log
    assert f"'content_length': {len(response.content)}" in response_log
    assert "'body': {'keys':" in response_log
    assert "public-modulus-21502" in response_log


async def test_mobile_id_non_verbose_logs_keep_kyc_content_encrypted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "mobile_id_verbose_logs", False)
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, content=b"response")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = MobileIdHttpProvider(http_client=client)
        mts_logger, log_stream, log_handler, previous_level = _capture_mobile_id_logs()
        try:
            await provider._request(
                "POST",
                "https://idgw.mobileid.mts.ru/oidc/kyc-match-split",
                mts_operation="kyc_match_split",
                mts_plaintext_content={
                    "birthdate": "1990-01-01",
                    "family_name": "Иванов",
                },
                content=b"encrypted-jwe",
                headers={"Authorization": "Bearer access-21502"},
            )
        finally:
            mts_logger.removeHandler(log_handler)
            mts_logger.setLevel(previous_level)

    assert requests[0].content == b"encrypted-jwe"
    request_log = next(
        line
        for line in log_stream.getvalue().splitlines()
        if "[ MTS ] request operation=kyc_match_split" in line
    )
    assert "<content 13 bytes>" in request_log
    assert "1990-01-01" not in request_log
    assert "Иванов" not in request_log
    assert "access-21502" not in request_log
    assert "'Authorization': '***'" in request_log


async def test_mobile_id_provider_maps_invalid_scope_to_user_message(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_private_key(tmp_path, "sig")
    monkeypatch.setattr(settings, "jwt_keys_dir", str(tmp_path))
    monkeypatch.setattr(settings, "mobile_id_sig_kid", "sig")
    monkeypatch.setattr(settings, "mobile_id_client_id", "mts_test_service")
    monkeypatch.setattr(settings, "mobile_id_notification_token", "notify-token")
    monkeypatch.setattr(settings, "api_url", "https://test.multileasing.ru")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={
                "error": "invalid_scope",
                "error_description": (
                    'Mandatory parameter scope "mc_kyc_plain" is missing '
                    "or invalid scope value"
                ),
            },
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://idgw.mobileid.mts.ru",
    ) as client:
        provider = MobileIdHttpProvider(http_client=client)
        with pytest.raises(
            MobileIdProviderUnavailableError,
            match="Mobile ID не принял параметры верификации",
        ) as exc_info:
            await provider.start(
                user_id=uuid4(),
                phone_number="+76662150232",
                birthdate=date(1990, 1, 1),
                correlation_id=uuid4(),
            )

    assert exc_info.value.status_code == 502
    assert "invalid_scope" not in str(exc_info.value)


async def test_enabled_mobile_id_provider_posts_sms_code() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = MobileIdHttpProvider(http_client=client)
        mts_logger, log_stream, log_handler, previous_level = _capture_mobile_id_logs()
        try:
            with pytest.raises(MobileIdProviderPendingError):
                await provider.submit_sms_code(
                    auth_req_id="auth-21502",
                    smsotp_endpoint="https://idgw.mobileid.mts.ru/verify/21502",
                    code="8492",
                    phone_number="+76662150232",
                    birthdate=date(1990, 1, 1),
                )
        finally:
            mts_logger.removeHandler(log_handler)
            mts_logger.setLevel(previous_level)

    assert requests[0].url.path == "/verify/21502"
    assert json.loads(requests[0].content) == {"verify_code": "8492"}
    log_text = log_stream.getvalue()
    assert "[ MTS ] request operation=sms_otp" in log_text
    assert "[ MTS ] response operation=sms_otp status_code=200" in log_text
    assert "8492" not in log_text
    assert "'verify_code': '***'" in log_text


async def test_mobile_id_provider_maps_wrong_sms_code_to_user_message() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={
                "error": "invalid_request",
                "error_description": "invalid request parameter verify_code",
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = MobileIdHttpProvider(http_client=client)
        with pytest.raises(
            MobileIdProviderUnavailableError,
            match="Неверный код подтверждения",
        ) as exc_info:
            await provider.submit_sms_code(
                auth_req_id="auth-21502",
                smsotp_endpoint="https://idgw.mobileid.mts.ru/verify/21502",
                code="8492",
                phone_number="+76662150232",
                birthdate=date(1990, 1, 1),
            )

    assert exc_info.value.status_code == 422


async def test_enabled_mobile_id_provider_verifies_id_token(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mts_sig_key = _write_private_key(tmp_path, "mts-sig")
    monkeypatch.setattr(settings, "jwt_keys_dir", str(tmp_path))
    monkeypatch.setattr(settings, "mobile_id_sig_kid", "mts-sig")
    monkeypatch.setattr(settings, "mobile_id_client_id", "mts_test_service")

    sig_jwk = _public_jwk(mts_sig_key, "rsa1", "sig", "RS256")
    id_token = jwt.encode(
        {
            "sub": "mobile-id-sub-21502",
            "iss": settings.mobile_id_issuer,
            "aud": "mts_test_service",
            "iat": int(datetime.now(UTC).timestamp()),
            "exp": int((datetime.now(UTC) + timedelta(minutes=5)).timestamp()),
        },
        _private_key_pem(mts_sig_key),
        algorithm="RS256",
        headers={"kid": "rsa1"},
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oidc/jwks":
            return httpx.Response(200, json={"keys": [sig_jwk]})
        msg = f"Unexpected Mobile ID test request: {request.url}"
        raise AssertionError(msg)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://idgw.mobileid.mts.ru",
    ) as client:
        provider = MobileIdHttpProvider(http_client=client)
        data = await provider.handle_notification(
            id_token=id_token,
            access_token="access-21502",
            jwks_uri=None,
            phone_number="+76662150232",
            birthdate=None,
        )

    assert data.mobile_id_sub == "mobile-id-sub-21502"
    assert data.phone_number == "+76662150232"
    assert data.birthdate_match is None


async def test_enabled_mobile_id_provider_verifies_id_token_at_hash(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mts_sig_key = _write_private_key(tmp_path, "mts-sig")
    monkeypatch.setattr(settings, "jwt_keys_dir", str(tmp_path))
    monkeypatch.setattr(settings, "mobile_id_sig_kid", "mts-sig")
    monkeypatch.setattr(settings, "mobile_id_client_id", "mts_test_service")

    access_token = "access-21502"
    sig_jwk = _public_jwk(mts_sig_key, "rsa1", "sig", "RS256")
    id_token = jwt.encode(
        {
            "sub": "mobile-id-sub-21502",
            "iss": settings.mobile_id_issuer,
            "aud": "mts_test_service",
            "iat": int(datetime.now(UTC).timestamp()),
            "exp": int((datetime.now(UTC) + timedelta(minutes=5)).timestamp()),
        },
        _private_key_pem(mts_sig_key),
        algorithm="RS256",
        headers={"kid": "rsa1"},
        access_token=access_token,
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oidc/jwks":
            return httpx.Response(200, json={"keys": [sig_jwk]})
        msg = f"Unexpected Mobile ID test request: {request.url}"
        raise AssertionError(msg)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://idgw.mobileid.mts.ru",
    ) as client:
        provider = MobileIdHttpProvider(http_client=client)
        data = await provider.handle_notification(
            id_token=id_token,
            access_token=access_token,
            jwks_uri=None,
            phone_number="+76662150232",
            birthdate=None,
        )

    assert data.mobile_id_sub == "mobile-id-sub-21502"


async def test_enabled_mobile_id_provider_falls_back_to_notification_jwks_for_sig(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    static_sig_key = _write_private_key(tmp_path, "static-sig")
    notification_sig_key = _write_private_key(tmp_path, "notification-sig")
    monkeypatch.setattr(settings, "jwt_keys_dir", str(tmp_path))
    monkeypatch.setattr(settings, "mobile_id_sig_kid", "static-sig")
    monkeypatch.setattr(settings, "mobile_id_client_id", "mts_test_service")

    id_token = jwt.encode(
        {
            "sub": "mobile-id-sub-21502",
            "iss": settings.mobile_id_issuer,
            "aud": "mts_test_service",
            "iat": int(datetime.now(UTC).timestamp()),
            "exp": int((datetime.now(UTC) + timedelta(minutes=5)).timestamp()),
        },
        _private_key_pem(notification_sig_key),
        algorithm="RS256",
        headers={"kid": "notification-sig"},
    )
    static_sig_jwk = _public_jwk(static_sig_key, "static-sig", "sig", "RS256")
    notification_sig_jwk = _public_jwk(
        notification_sig_key,
        "notification-sig",
        "sig",
        "RS256",
    )
    seen_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_paths.append(f"{request.method} {request.url.path}")
        if request.url.path == "/oidc/jwks":
            return httpx.Response(200, json={"keys": [static_sig_jwk]})
        if request.url.path == "/mc/oidc/jwks":
            return httpx.Response(200, json={"keys": [notification_sig_jwk]})
        msg = f"Unexpected Mobile ID test request: {request.url}"
        raise AssertionError(msg)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://idgw.mobileid.mts.ru",
    ) as client:
        provider = MobileIdHttpProvider(http_client=client)
        data = await provider.handle_notification(
            id_token=id_token,
            access_token="access-21502",
            jwks_uri="https://idgw.mobileid.mts.ru/mc/oidc/jwks",
            phone_number="+76662150232",
            birthdate=None,
        )

    assert data.mobile_id_sub == "mobile-id-sub-21502"
    assert seen_paths == ["GET /oidc/jwks", "GET /mc/oidc/jwks"]


async def test_enabled_mobile_id_provider_matches_profile_fields_via_kyc_jwe(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mts_sig_key = _write_private_key(tmp_path, "mts-sig")
    service_enc_key = _write_private_key(tmp_path, "service-enc")
    operator_enc_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    for setting_name, value in (
        ("jwt_keys_dir", str(tmp_path)),
        ("mobile_id_sig_kid", "mts-sig"),
        ("mobile_id_enc_kid", "service-enc"),
        ("mobile_id_client_id", "mts_test_service"),
        ("mobile_id_verbose_logs", True),
    ):
        monkeypatch.setattr(settings, setting_name, value)

    id_token = jwt.encode(
        {
            "sub": "mobile-id-sub-21502",
            "iss": settings.mobile_id_issuer,
            "aud": "mts_test_service",
            "iat": int(datetime.now(UTC).timestamp()),
            "exp": int((datetime.now(UTC) + timedelta(minutes=5)).timestamp()),
        },
        _private_key_pem(mts_sig_key),
        algorithm="RS256",
        headers={"kid": "mts-sig"},
    )
    mts_sig_jwk = _public_jwk(mts_sig_key, "mts-sig", "sig", "RS256")
    operator_enc_jwk = _public_jwk(
        operator_enc_key,
        "operator-enc",
        "enc",
        "RSA-OAEP",
    )
    service_enc_jwk = _public_jwk(
        service_enc_key,
        "service-enc",
        "enc",
        "RSA-OAEP",
    )
    kyc_request_bodies: list[bytes] = []

    mts_logger, log_stream, log_handler, previous_level = _capture_mobile_id_logs()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oidc/jwks":
            return httpx.Response(200, json={"keys": [mts_sig_jwk]})
        if request.url.path == "/kyc-jwks":
            return httpx.Response(200, json={"keys": [operator_enc_jwk]})
        if request.url.path == "/oidc/kyc-match-split":
            kyc_request_bodies.append(request.content)
            assert request.headers["Authorization"] == "Bearer access-21502"
            request_payload = json.loads(
                jwe.decrypt(request.content, _private_key_pem(operator_enc_key))
                .decode("utf-8")
            )
            assert request_payload == {
                "birthdate": "1990-01-01",
                "family_name": "Иванов",
                "given_name": "Иван",
                "middle_name": "Иванович",
            }
            response_token = jwe.encrypt(
                json.dumps(
                    {
                        "sub": "mobile-id-sub-21502",
                        "birthdate_match": "Y",
                        "family_name_match": "Y",
                        "given_name_match": "Y",
                        "middle_name_match": "Y",
                    },
                    ensure_ascii=False,
                ),
                service_enc_jwk,
                algorithm="RSA-OAEP",
                encryption="A256GCM",
                kid="service-enc",
            )
            return httpx.Response(
                200,
                content=response_token,
                headers={"Content-Type": "application/jwt"},
            )
        msg = f"Unexpected Mobile ID test request: {request.url}"
        raise AssertionError(msg)

    try:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            base_url="https://idgw.mobileid.mts.ru",
        ) as client:
            provider = MobileIdHttpProvider(http_client=client)
            data = await provider.handle_notification(
                id_token=id_token,
                access_token="access-21502",
                jwks_uri="https://operator.example/kyc-jwks",
                phone_number="+76662150232",
                birthdate=date(1990, 1, 1),
                family_name="Иванов",
                given_name="Иван",
                middle_name="Иванович",
            )
    finally:
        mts_logger.removeHandler(log_handler)
        mts_logger.setLevel(previous_level)

    assert data.mobile_id_sub == "mobile-id-sub-21502"
    assert data.birthdate == date(1990, 1, 1)
    assert data.birthdate_match == "Y"
    assert data.family_name == "Иванов"
    assert data.given_name == "Иван"
    assert data.middle_name == "Иванович"
    log_text = log_stream.getvalue()
    _assert_verbose_kyc_request_diagnostics(kyc_request_bodies, log_text)
    assert "[ MTS ] response_plain operation=decode_id_token" in log_text
    assert "'sub': 'mobile-id-sub-21502'" in log_text
    assert "[ MTS ] request_plain operation=kyc_match_split" not in log_text
    assert "'birthdate': '1990-01-01'" in log_text
    assert "[ MTS ] response_plain operation=kyc_match_split" in log_text
    assert "'birthdate_match': 'Y'" in log_text
    assert "'family_name': 'Иванов'" in log_text
    assert "'body': {'keys':" in log_text
    assert mts_sig_jwk["n"] in log_text
    assert operator_enc_jwk["n"] in log_text


async def test_enabled_mobile_id_provider_uses_notification_jwks_uri_for_kyc(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mts_sig_key = _write_private_key(tmp_path, "mts-sig")
    service_enc_key = _write_private_key(tmp_path, "service-enc")
    operator_enc_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    monkeypatch.setattr(settings, "jwt_keys_dir", str(tmp_path))
    monkeypatch.setattr(settings, "mobile_id_sig_kid", "mts-sig")
    monkeypatch.setattr(settings, "mobile_id_enc_kid", "service-enc")
    monkeypatch.setattr(settings, "mobile_id_client_id", "mts_test_service")

    id_token = jwt.encode(
        {
            "sub": "mobile-id-sub-21502",
            "iss": settings.mobile_id_issuer,
            "aud": "mts_test_service",
            "iat": int(datetime.now(UTC).timestamp()),
            "exp": int((datetime.now(UTC) + timedelta(minutes=5)).timestamp()),
        },
        _private_key_pem(mts_sig_key),
        algorithm="RS256",
        headers={"kid": "mts-sig"},
    )
    mts_sig_jwk = _public_jwk(mts_sig_key, "mts-sig", "sig", "RS256")
    operator_enc_jwk = _public_jwk(
        operator_enc_key,
        "enc-rsa-idgw-1",
        "enc",
        "RSA-OAEP-256",
    )
    service_enc_jwk = _public_jwk(
        service_enc_key,
        "service-enc",
        "enc",
        "RSA-OAEP",
    )
    seen_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_paths.append(f"{request.method} {request.url.path}")
        if request.url.path == "/oidc/jwks":
            return httpx.Response(200, json={"keys": [mts_sig_jwk]})
        if request.url.path == "/kyc-jwks":
            return httpx.Response(200, json={"keys": [operator_enc_jwk]})
        if request.url.path == "/oidc/kyc-match-split":
            request_payload = json.loads(
                jwe.decrypt(request.content, _private_key_pem(operator_enc_key))
                .decode("utf-8")
            )
            assert request_payload == {
                "birthdate": "1990-01-01",
                "family_name": "Иванов",
                "given_name": "Иван",
                "middle_name": "Иванович",
            }
            response_token = jwe.encrypt(
                json.dumps(
                    {
                        "sub": "mobile-id-sub-21502",
                        "birthdate_match": "Y",
                        "family_name_match": "Y",
                        "given_name_match": "Y",
                        "middle_name_match": "Y",
                    },
                    ensure_ascii=False,
                ),
                service_enc_jwk,
                algorithm="RSA-OAEP",
                encryption="A256GCM",
                kid="service-enc",
            )
            return httpx.Response(
                200,
                content=response_token,
                headers={"Content-Type": "application/jwt"},
            )
        msg = f"Unexpected Mobile ID test request: {request.url}"
        raise AssertionError(msg)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://idgw.mobileid.mts.ru",
    ) as client:
        provider = MobileIdHttpProvider(http_client=client)
        data = await provider.handle_notification(
            id_token=id_token,
            access_token="access-21502",
            jwks_uri="https://operator.example/kyc-jwks",
            phone_number="+76662150232",
            birthdate=date(1990, 1, 1),
            family_name="Иванов",
            given_name="Иван",
            middle_name="Иванович",
        )

    assert data.mobile_id_sub == "mobile-id-sub-21502"
    assert seen_paths == [
        "GET /oidc/jwks",
        "GET /kyc-jwks",
        "POST /oidc/kyc-match-split",
    ]


async def test_enabled_mobile_id_provider_does_not_fallback_to_static_jwks_for_kyc(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mts_sig_key = _write_private_key(tmp_path, "mts-sig")
    monkeypatch.setattr(settings, "jwt_keys_dir", str(tmp_path))
    monkeypatch.setattr(settings, "mobile_id_sig_kid", "mts-sig")
    monkeypatch.setattr(settings, "mobile_id_client_id", "mts_test_service")

    id_token = jwt.encode(
        {
            "sub": "mobile-id-sub-21502",
            "iss": settings.mobile_id_issuer,
            "aud": "mts_test_service",
            "iat": int(datetime.now(UTC).timestamp()),
            "exp": int((datetime.now(UTC) + timedelta(minutes=5)).timestamp()),
        },
        _private_key_pem(mts_sig_key),
        algorithm="RS256",
        headers={"kid": "mts-sig"},
    )
    mts_sig_jwk = _public_jwk(mts_sig_key, "mts-sig", "sig", "RS256")
    seen_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_paths.append(f"{request.method} {request.url.path}")
        if request.url.path == "/oidc/jwks":
            return httpx.Response(200, json={"keys": [mts_sig_jwk]})
        msg = f"Unexpected Mobile ID test request: {request.url}"
        raise AssertionError(msg)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://idgw.mobileid.mts.ru",
    ) as client:
        provider = MobileIdHttpProvider(http_client=client)
        with pytest.raises(
            MobileIdProviderUnavailableError,
            match="Mobile ID прислал некорректное подтверждение",
        ):
            await provider.handle_notification(
                id_token=id_token,
                access_token="access-21502",
                jwks_uri="https://idgw.mobileid.mts.ru/oidc/jwks",
                phone_number="+76662150232",
                birthdate=date(1990, 1, 1),
                family_name="Иванов",
                given_name="Иван",
            )
    assert seen_paths == ["GET /oidc/jwks", "GET /oidc/jwks"]


async def test_enabled_mobile_id_provider_rejects_non_matching_birthdate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mts_sig_key = _write_private_key(tmp_path, "mts-sig")
    service_enc_key = _write_private_key(tmp_path, "service-enc")
    operator_enc_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    monkeypatch.setattr(settings, "jwt_keys_dir", str(tmp_path))
    monkeypatch.setattr(settings, "mobile_id_sig_kid", "mts-sig")
    monkeypatch.setattr(settings, "mobile_id_enc_kid", "service-enc")
    monkeypatch.setattr(settings, "mobile_id_client_id", "mts_test_service")

    id_token = jwt.encode(
        {
            "sub": "mobile-id-sub-21502",
            "iss": settings.mobile_id_issuer,
            "aud": "mts_test_service",
            "iat": int(datetime.now(UTC).timestamp()),
            "exp": int((datetime.now(UTC) + timedelta(minutes=5)).timestamp()),
        },
        _private_key_pem(mts_sig_key),
        algorithm="RS256",
        headers={"kid": "mts-sig"},
    )
    mts_sig_jwk = _public_jwk(mts_sig_key, "mts-sig", "sig", "RS256")
    operator_enc_jwk = _public_jwk(
        operator_enc_key,
        "operator-enc",
        "enc",
        "RSA-OAEP",
    )
    service_enc_jwk = _public_jwk(
        service_enc_key,
        "service-enc",
        "enc",
        "RSA-OAEP",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/oidc/jwks":
            return httpx.Response(200, json={"keys": [mts_sig_jwk]})
        if request.url.path == "/kyc-jwks":
            return httpx.Response(200, json={"keys": [operator_enc_jwk]})
        if request.url.path == "/oidc/kyc-match-split":
            response_token = jwe.encrypt(
                json.dumps(
                    {
                        "sub": "mobile-id-sub-21502",
                        "birthdate_match": "N-AV",
                        "family_name_match": "Y",
                        "given_name_match": "Y",
                    },
                    ensure_ascii=False,
                ),
                service_enc_jwk,
                algorithm="RSA-OAEP",
                encryption="A256GCM",
                kid="service-enc",
            )
            return httpx.Response(
                200,
                content=response_token,
                headers={"Content-Type": "application/jwt"},
            )
        msg = f"Unexpected Mobile ID test request: {request.url}"
        raise AssertionError(msg)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://idgw.mobileid.mts.ru",
    ) as client:
        provider = MobileIdHttpProvider(http_client=client)
        with pytest.raises(
            MobileIdProviderUnavailableError,
            match="Данные профиля не совпали с данными Mobile ID",
        ):
            await provider.handle_notification(
                id_token=id_token,
                access_token="access-21502",
                jwks_uri="https://operator.example/kyc-jwks",
                phone_number="+76662150232",
                birthdate=date(1990, 1, 1),
                family_name="Иванов",
                given_name="Иван",
            )
