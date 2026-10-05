from __future__ import annotations

import json
import logging
import re
from collections.abc import Mapping
from datetime import UTC, date, datetime, timedelta
from typing import Any, cast
from uuid import UUID, uuid4

import httpx
from jose import jwe, jwt
from jose.exceptions import JWTError

from domain.services.identity_verification import (
    IdentityVerificationData,
    IdentityVerificationProvider,
    IdentityVerificationStarted,
)
from infrastructure.services.mobile_id.keys import mobile_id_private_key_pem
from infrastructure.settings import settings

logger = logging.getLogger("carcraft-backend")

_MTS_LOG_PREFIX = "[ MTS ]"
_MTS_REDACTED = "***"
_MOBILE_ID_JWE_KEY_ALGORITHMS = {"RSA-OAEP", "RSA-OAEP-256"}
_MTS_SENSITIVE_KEYS = frozenset(
    {
        "access_token",
        "authorization",
        "client_assertion",
        "client_notification_token",
        "client_secret",
        "code",
        "id_token",
        "request",
        "token",
        "verify_code",
    }
)
_MTS_SENSITIVE_KEY_SUFFIXES = ("_token", "_secret", "_assertion")
_MTS_LOG_STRING_LIMIT = 500
_COMPACT_JOSE_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_-])"
    r"[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{2,}\.[A-Za-z0-9_-]{8,}"
    r"(?:\.[A-Za-z0-9_-]{2,}\.[A-Za-z0-9_-]{8,})?"
    r"(?![A-Za-z0-9_-])"
)
_BEARER_TOKEN_PATTERN = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+")
_AUTHORIZATION_VALUE_PATTERN = re.compile(
    r"(?im)(\bauthorization\b[\"']?\s*[:=]\s*[\"']?)[^\r\n]+"
)
_NAMED_SECRET_PATTERN = re.compile(
    r"(?i)(\b(?:request|token|verify_code|code|"
    r"[A-Za-z][A-Za-z0-9_]*(?:_token|_secret|_assertion))"
    r"\b[\"']?\s*[:=]\s*[\"']?)[^\"'\s,;&}]+"
)


class MobileIdProviderUnavailableError(RuntimeError):
    def __init__(self, message: str, *, status_code: int = 503) -> None:
        super().__init__(message)
        self.status_code = status_code


class MobileIdProviderPendingError(RuntimeError):
    pass


def _mask_phone(phone: str) -> str:
    digits = "".join(ch for ch in phone if ch.isdigit())
    suffix = digits[-3:] if len(digits) >= 3 else digits
    return f"+7 *** *** *{suffix}" if suffix else "***"


class LocalMobileIdProvider:
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
        _ = (user_id, birthdate, family_name, given_name, middle_name)
        return IdentityVerificationStarted(
            auth_req_id=f"local-{correlation_id}",
            phone_masked=_mask_phone(phone_number),
            expires_at=datetime.now(UTC)
            + timedelta(seconds=settings.mobile_id_attempt_ttl_seconds),
        )

    async def submit_sms_code(
        self,
        *,
        auth_req_id: str | None,
        smsotp_endpoint: str | None,
        code: str,
        phone_number: str | None,
        birthdate: date | None,
    ) -> IdentityVerificationData:
        _ = smsotp_endpoint
        if code != "0000":
            raise MobileIdProviderUnavailableError(
                "Неверный код подтверждения. Проверьте SMS и попробуйте ещё раз.",
                status_code=422,
            )
        return IdentityVerificationData(
            mobile_id_sub=auth_req_id or "local-mobile-id",
            phone_number=phone_number,
            birthdate=birthdate,
            birthdate_match="Y",
        )

    async def handle_notification(
        self,
        *,
        id_token: str,
        access_token: str,
        jwks_uri: str | None,
        phone_number: str | None,
        birthdate: date | None,
        family_name: str | None = None,
        given_name: str | None = None,
        middle_name: str | None = None,
    ) -> IdentityVerificationData:
        _ = jwks_uri
        return IdentityVerificationData(
            mobile_id_sub=id_token or access_token or "local-mobile-id",
            phone_number=phone_number,
            birthdate=birthdate,
            birthdate_match="Y",
            family_name=family_name,
            given_name=given_name,
            middle_name=middle_name,
        )

def _mobile_id_public_url(configured: str, setting_name: str) -> str:
    clean = configured.strip()
    if clean.startswith(("http://", "https://")):
        return clean
    if not clean:
        msg = f"Mobile ID setting {setting_name} is required"
        raise MobileIdProviderUnavailableError(msg)
    if not clean.startswith("/"):
        msg = (
            f"Mobile ID setting {setting_name} must be an absolute URL "
            "or an absolute path"
        )
        raise MobileIdProviderUnavailableError(msg)
    base = (settings.public_url or settings.api_url).rstrip("/")
    if not base:
        msg = "Mobile ID public URL base is not configured"
        raise MobileIdProviderUnavailableError(msg)
    if clean == "/":
        return base
    return f"{base}{clean}"


def _mobile_id_oidc_url(path: str) -> str:
    base = settings.mobile_id_base_url.strip().rstrip("/")
    if not base:
        msg = "mobile_id_base_url is required"
        raise MobileIdProviderUnavailableError(msg, status_code=500)
    return f"{base}/{path.lstrip('/')}"


def _mobile_id_oidc_jwks_url() -> str:
    return _mobile_id_oidc_url("jwks")


def _mobile_id_signature_jwks_urls(notification_jwks_uri: str | None) -> list[str]:
    urls = [_mobile_id_oidc_jwks_url()]
    if notification_jwks_uri and notification_jwks_uri not in urls:
        urls.append(notification_jwks_uri)
    return urls


def _is_jwe_encryption_key(key: Mapping[str, Any]) -> bool:
    return (
        key.get("use") == "enc"
        or str(key.get("alg") or "") in _MOBILE_ID_JWE_KEY_ALGORITHMS
    )


def _jwe_algorithm_for_key(key: Mapping[str, Any]) -> str:
    alg = str(key.get("alg") or "")
    if alg in _MOBILE_ID_JWE_KEY_ALGORITHMS:
        return alg
    return "RSA-OAEP"


def _normalize_phone(phone: str) -> str:
    return "".join(ch for ch in phone if ch.isdigit())


def _plain_msisdn_login_hint(phone: str) -> str:
    return f"MSISDN:{_normalize_phone(phone)}"


def _required(value: str, name: str) -> str:
    clean = value.strip()
    if not clean:
        raise MobileIdProviderUnavailableError(f"Mobile ID setting {name} is required")
    return clean


def _json_error(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return response.text
    if isinstance(payload, Mapping):
        description = payload.get("error_description") or payload.get("message")
        code = payload.get("error")
        if description and code:
            return f"{code}: {description}"
        if description:
            return str(description)
        if code:
            return str(code)
    return str(payload)


def _mobile_id_error_parts(response: httpx.Response) -> tuple[str, str]:
    try:
        payload = response.json()
    except ValueError:
        return "", response.text
    if not isinstance(payload, Mapping):
        return "", str(payload)
    code = str(payload.get("error") or payload.get("code") or "")
    description = str(
        payload.get("error_description")
        or payload.get("message")
        or payload.get("detail")
        or ""
    )
    return code, description


def _provider_error_from_response(
    response: httpx.Response,
    *,
    operation: str,
) -> MobileIdProviderUnavailableError:
    code, description = _mobile_id_error_parts(response)
    text = f"{code} {description}".lower()
    if any(marker in text for marker in ("verify_code", "wrong code", "invalid code")):
        return MobileIdProviderUnavailableError(
            "Неверный код подтверждения. Проверьте SMS и попробуйте ещё раз.",
            status_code=422,
        )
    if any(marker in text for marker in ("expired", "истек", "истёк")):
        return MobileIdProviderUnavailableError(
            "Срок действия кода истёк. Запустите верификацию заново.",
            status_code=410,
        )
    if code == "invalid_scope":
        return MobileIdProviderUnavailableError(
            "Mobile ID не принял параметры верификации. "
            "Попробуйте позже или обратитесь в поддержку.",
            status_code=502,
        )
    if code in {"invalid_request", "unauthorized_client", "access_denied"}:
        return MobileIdProviderUnavailableError(
            "Mobile ID отклонил запрос верификации. "
            "Проверьте данные профиля и попробуйте ещё раз.",
            status_code=502,
        )
    if operation == "sms_otp":
        return MobileIdProviderUnavailableError(
            "Не удалось проверить SMS-код через Mobile ID. Попробуйте ещё раз.",
            status_code=502,
        )
    return MobileIdProviderUnavailableError(
        "Mobile ID временно не смог выполнить верификацию. "
        "Попробуйте позже или обратитесь в поддержку.",
        status_code=502,
    )


def _redact_mts_log_string(value: str) -> str:
    if "PRIVATE KEY-----" in value:
        return _MTS_REDACTED
    redacted = _BEARER_TOKEN_PATTERN.sub("Bearer ***", value)
    redacted = _AUTHORIZATION_VALUE_PATTERN.sub(r"\1***", redacted)
    redacted = _NAMED_SECRET_PATTERN.sub(r"\1***", redacted)
    redacted = _COMPACT_JOSE_PATTERN.sub(_MTS_REDACTED, redacted)
    if not settings.mobile_id_verbose_logs and len(redacted) > _MTS_LOG_STRING_LIMIT:
        return f"{redacted[:120]}...<truncated {len(redacted)} chars>"
    return redacted


def _redact_mts_log_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): (
                _MTS_REDACTED
                if _is_mts_sensitive_key(str(key))
                else _redact_mts_log_value(item)
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact_mts_log_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_redact_mts_log_value(item) for item in value)
    if isinstance(value, str):
        return _redact_mts_log_string(value)
    return value


def _is_mts_sensitive_key(key: str) -> bool:
    normalized = key.lower()
    return normalized in _MTS_SENSITIVE_KEYS or normalized.endswith(
        _MTS_SENSITIVE_KEY_SUFFIXES
    )


def _summarize_mts_content(content: Any) -> str:
    if isinstance(content, str):
        return f"<content {len(content)} chars>"
    if isinstance(content, bytes):
        return f"<content {len(content)} bytes>"
    return f"<content type={type(content).__name__}>"


def _mts_request_payload(
    kwargs: Mapping[str, Any],
    *,
    plaintext_content: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    if "headers" in kwargs:
        payload["headers"] = _redact_mts_log_value(dict(kwargs["headers"]))
    if "params" in kwargs:
        payload["params"] = _redact_mts_log_value(kwargs["params"])
    if "json" in kwargs:
        payload["json"] = _redact_mts_log_value(kwargs["json"])
    if "content" in kwargs and kwargs["content"] is not None:
        if settings.mobile_id_verbose_logs and plaintext_content is not None:
            payload["content"] = _redact_mts_log_value(dict(plaintext_content))
        else:
            payload["content"] = _summarize_mts_content(kwargs["content"])
    return payload


def _mts_jwks_response_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    keys = payload.get("keys")
    if not isinstance(keys, list):
        return {"keys_count": None, "keys_summary": "<invalid keys>"}
    summary: list[dict[str, Any]] = []
    for key in keys:
        if not isinstance(key, Mapping):
            continue
        summary.append(
            {
                "kid": key.get("kid"),
                "use": key.get("use"),
                "alg": key.get("alg"),
                "kty": key.get("kty"),
            }
        )
    return {"keys_count": len(keys), "keys_summary": summary}


def _mts_json_response_payload(payload: Any, *, operation: str) -> Any:
    if (
        operation == "fetch_jwks"
        and not settings.mobile_id_verbose_logs
        and isinstance(payload, Mapping)
    ):
        return _mts_jwks_response_payload(payload)
    return _redact_mts_log_value(payload)


def _mts_response_media_type(response: httpx.Response) -> str:
    content_type = str(response.headers.get("content-type", ""))
    return content_type.partition(";")[0].strip().lower()


def _mts_readable_response_body(response: httpx.Response) -> Any | None:
    if not response.content:
        return None
    media_type = _mts_response_media_type(response)
    if media_type == "application/json" or media_type.endswith("+json"):
        try:
            return _redact_mts_log_value(response.json())
        except ValueError:
            return {
                "format": "invalid_json",
                "text": _redact_mts_log_value(response.text),
            }
    if media_type.startswith("text/"):
        return _redact_mts_log_value(response.text)
    return None


def _mts_response_payload(response: httpx.Response, *, operation: str) -> Any:
    if not response.content:
        return None
    media_type = _mts_response_media_type(response)
    readable_body = _mts_readable_response_body(response)
    if readable_body is not None:
        is_standard_json = media_type == "application/json"
        is_verbose_json = settings.mobile_id_verbose_logs and media_type.endswith("json")
        if is_standard_json or is_verbose_json:
            if (
                not settings.mobile_id_verbose_logs
                and isinstance(readable_body, Mapping)
                and readable_body.get("format") == "invalid_json"
            ):
                return "<invalid json response>"
            readable_body = _mts_json_response_payload(
                readable_body,
                operation=operation,
            )
        if settings.mobile_id_verbose_logs:
            return {
                "content_type": media_type,
                "content_length": len(response.content),
                "body": readable_body,
            }
        if is_standard_json or is_verbose_json:
            return readable_body
    content_type = response.headers.get("content-type", "")
    return f"<response {len(response.content)} bytes content_type={content_type or 'unknown'}>"


def _mts_request_claims_for_log(payload: Mapping[str, Any], sig_kid: str) -> dict[str, Any]:
    safe_claim_names = (
        "iss",
        "aud",
        "client_id",
        "response_type",
        "scope",
        "version",
        "notification_uri",
        "sms_otp_notification_uri",
        "jwks_public_url",
        "acr_values",
        "correlation_id",
    )
    claims = {name: payload.get(name) for name in safe_claim_names}
    claims["sig_kid"] = sig_kid
    return claims


class MobileIdHttpProvider:
    def __init__(self, http_client: httpx.AsyncClient | None = None) -> None:
        self._http_client = http_client

    async def _request(
        self,
        method: str,
        url: str,
        *,
        mts_operation: str,
        mts_plaintext_content: Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> httpx.Response:
        request_payload = _mts_request_payload(
            kwargs,
            plaintext_content=mts_plaintext_content,
        )
        logger.info(
            "%s request operation=%s method=%s url=%s payload=%s",
            _MTS_LOG_PREFIX,
            mts_operation,
            method,
            url,
            request_payload,
        )
        if self._http_client is not None:
            try:
                response = await self._http_client.request(method, url, **kwargs)
            except httpx.HTTPError as exc:
                logger.warning(
                    "%s error operation=%s method=%s url=%s error=%s",
                    _MTS_LOG_PREFIX,
                    mts_operation,
                    method,
                    url,
                    exc,
                )
                raise
            logger.info(
                "%s response operation=%s status_code=%s url=%s payload=%s",
                _MTS_LOG_PREFIX,
                mts_operation,
                response.status_code,
                url,
                _mts_response_payload(response, operation=mts_operation),
            )
            return response
        timeout = httpx.Timeout(settings.mobile_id_request_timeout_seconds)
        async with httpx.AsyncClient(timeout=timeout) as client:
            try:
                response = await client.request(method, url, **kwargs)
            except httpx.HTTPError as exc:
                logger.warning(
                    "%s error operation=%s method=%s url=%s error=%s",
                    _MTS_LOG_PREFIX,
                    mts_operation,
                    method,
                    url,
                    exc,
                )
                raise
            logger.info(
                "%s response operation=%s status_code=%s url=%s payload=%s",
                _MTS_LOG_PREFIX,
                mts_operation,
                response.status_code,
                url,
                _mts_response_payload(response, operation=mts_operation),
            )
            return response

    def _signed_request_object(
        self,
        *,
        phone_number: str,
        correlation_id: UUID,
    ) -> str:
        client_id = _required(settings.mobile_id_client_id, "mobile_id_client_id")
        notification_token = _required(
            settings.mobile_id_notification_token,
            "mobile_id_notification_token",
        )
        sig_kid = _required(settings.mobile_id_sig_kid, "mobile_id_sig_kid")
        payload = {
            "nonce": str(uuid4()),
            "iss": client_id,
            "aud": settings.mobile_id_audience,
            "client_id": client_id,
            "response_type": "mc_si_async_code",
            "scope": settings.mobile_id_scope,
            "version": settings.mobile_id_request_version,
            "notification_uri": _mobile_id_public_url(
                settings.mobile_id_notification_uri,
                "mobile_id_notification_uri",
            ),
            "sms_otp_notification_uri": _mobile_id_public_url(
                settings.mobile_id_sms_otp_notification_uri,
                "mobile_id_sms_otp_notification_uri",
            ),
            "jwks_public_url": _mobile_id_public_url(
                settings.mobile_id_jwks_public_url,
                "mobile_id_jwks_public_url",
            ),
            "acr_values": settings.mobile_id_acr_values,
            "client_notification_token": notification_token,
            "login_hint": _plain_msisdn_login_hint(phone_number),
            "correlation_id": str(correlation_id),
        }
        logger.info(
            "%s request_claims operation=si_authorize payload=%s",
            _MTS_LOG_PREFIX,
            _mts_request_claims_for_log(payload, sig_kid),
        )
        return cast(
            "str",
            jwt.encode(
                payload,
                mobile_id_private_key_pem(sig_kid),
                algorithm="RS256",
                headers={"kid": sig_kid, "typ": "JWT"},
            ),
        )

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
        _ = (user_id, birthdate, family_name, given_name, middle_name)
        client_id = _required(settings.mobile_id_client_id, "mobile_id_client_id")
        payload = {
            "client_id": client_id,
            "response_type": "mc_si_async_code",
            "scope": settings.mobile_id_scope,
            "request": self._signed_request_object(
                phone_number=phone_number,
                correlation_id=correlation_id,
            ),
            "correlation_id": str(correlation_id),
        }
        url = f"{settings.mobile_id_base_url.rstrip('/')}/si-authorize"
        try:
            response = await self._request(
                "POST",
                url,
                mts_operation="si_authorize",
                json=payload,
            )
        except httpx.HTTPError as exc:
            raise MobileIdProviderUnavailableError(
                "Не удалось связаться с Mobile ID. Попробуйте позже.",
                status_code=503,
            ) from exc
        if response.status_code >= 400:
            raise _provider_error_from_response(response, operation="si_authorize")
        body = response.json()
        auth_req_id = str(body.get("auth_req_id") or "")
        if not auth_req_id:
            raise MobileIdProviderUnavailableError(
                "Mobile ID не вернул идентификатор проверки. Попробуйте позже.",
                status_code=502,
            )
        expires_in = int(body.get("expires_in") or settings.mobile_id_attempt_ttl_seconds)
        return IdentityVerificationStarted(
            auth_req_id=auth_req_id,
            phone_masked=_mask_phone(phone_number),
            expires_at=datetime.now(UTC) + timedelta(seconds=expires_in),
        )

    async def submit_sms_code(
        self,
        *,
        auth_req_id: str | None,
        smsotp_endpoint: str | None,
        code: str,
        phone_number: str | None,
        birthdate: date | None,
    ) -> IdentityVerificationData:
        _ = (auth_req_id, phone_number, birthdate)
        if not smsotp_endpoint:
            raise MobileIdProviderUnavailableError(
                "SMS-код ещё не готов. Дождитесь сообщения и попробуйте снова.",
                status_code=409,
            )
        try:
            response = await self._request(
                "POST",
                smsotp_endpoint,
                mts_operation="sms_otp",
                json={"verify_code": code},
                headers={"Content-Type": "application/json"},
            )
        except httpx.HTTPError as exc:
            raise MobileIdProviderUnavailableError(
                "Не удалось связаться с Mobile ID. Попробуйте позже.",
                status_code=503,
            ) from exc
        if response.status_code >= 400:
            raise _provider_error_from_response(response, operation="sms_otp")
        raise MobileIdProviderPendingError(
            "Код принят. Ожидаем подтверждение Mobile ID."
        )

    async def _fetch_jwks(self, jwks_uri: str | None) -> list[dict[str, Any]]:
        url = jwks_uri or _mobile_id_oidc_jwks_url()
        response = await self._request("GET", url, mts_operation="fetch_jwks")
        if response.status_code >= 400:
            raise _provider_error_from_response(response, operation="fetch_jwks")
        keys = response.json().get("keys", [])
        if not isinstance(keys, list):
            raise MobileIdProviderUnavailableError(
                "Mobile ID прислал некорректное подтверждение. "
                "Попробуйте пройти верификацию заново.",
                status_code=502,
            )
        return [key for key in keys if isinstance(key, dict)]

    async def _fetch_jwe_encryption_keys(
        self,
        jwks_uri: str | None,
    ) -> list[dict[str, Any]]:
        if not jwks_uri:
            raise MobileIdProviderUnavailableError(
                "Mobile ID прислал неполное подтверждение. "
                "Попробуйте пройти верификацию заново.",
                status_code=502,
            )
        return [
            key for key in await self._fetch_jwks(jwks_uri) if _is_jwe_encryption_key(key)
        ]

    async def _decode_id_token(
        self,
        *,
        id_token: str,
        access_token: str,
        jwks_uri: str | None,
    ) -> dict[str, Any]:
        try:
            header = jwt.get_unverified_header(id_token)
        except JWTError as exc:
            raise MobileIdProviderUnavailableError(
                "Mobile ID прислал некорректное подтверждение. "
                "Попробуйте пройти верификацию заново.",
                status_code=502,
            ) from exc
        kid = header.get("kid")
        sig_jwks_urls = _mobile_id_signature_jwks_urls(jwks_uri)
        logger.info(
            "%s response_plain operation=id_token_header payload=%s",
            _MTS_LOG_PREFIX,
            {
                "alg": header.get("alg"),
                "kid": kid,
                "typ": header.get("typ"),
                "jwks_urls": sig_jwks_urls,
            },
        )
        last_error: Exception | None = None
        for sig_jwks_url in sig_jwks_urls:
            keys = await self._fetch_jwks(sig_jwks_url)
            candidates = [key for key in keys if not kid or key.get("kid") == kid]
            if not candidates:
                logger.warning(
                    "%s response_plain operation=decode_id_token_error payload=%s",
                    _MTS_LOG_PREFIX,
                    {
                        "reason": "matching_key_not_found",
                        "kid": kid,
                        "available_kids": [key.get("kid") for key in keys],
                        "jwks_url": sig_jwks_url,
                    },
                )
                continue
            for key in candidates:
                try:
                    decoded = dict(
                        jwt.decode(
                            id_token,
                            key,
                            algorithms=["RS256"],
                            audience=settings.mobile_id_client_id,
                            issuer=settings.mobile_id_issuer,
                            access_token=access_token,
                        )
                    )
                    logger.info(
                        "%s response_plain operation=decode_id_token payload=%s",
                        _MTS_LOG_PREFIX,
                        {"jwks_url": sig_jwks_url, **decoded},
                    )
                    return decoded
                except JWTError as exc:
                    last_error = exc
                    logger.warning(
                        "%s response_plain operation=decode_id_token_error payload=%s",
                        _MTS_LOG_PREFIX,
                        {
                            "reason": "jwt_decode_failed",
                            "kid": kid,
                            "key_kid": key.get("kid"),
                            "jwks_url": sig_jwks_url,
                            "error_type": type(exc).__name__,
                            "error": str(exc),
                        },
                    )
        raise MobileIdProviderUnavailableError(
            "Mobile ID прислал некорректное подтверждение. "
            "Попробуйте пройти верификацию заново.",
            status_code=502,
        ) from last_error

    async def _kyc_match_profile(
        self,
        *,
        access_token: str,
        jwks_uri: str | None,
        birthdate: date | None,
        family_name: str | None,
        given_name: str | None,
        middle_name: str | None,
    ) -> dict[str, Any]:
        enc_keys = await self._fetch_jwe_encryption_keys(jwks_uri)
        if not enc_keys:
            raise MobileIdProviderUnavailableError(
                "Mobile ID прислал некорректное подтверждение. "
                "Попробуйте пройти верификацию заново.",
                status_code=502,
            )
        kyc_payload: dict[str, str] = {}
        if birthdate is not None:
            kyc_payload["birthdate"] = birthdate.isoformat()
        kyc_payload.update(
            {
                field: value
                for field, value in {
                    "family_name": family_name,
                    "given_name": given_name,
                    "middle_name": middle_name,
                }.items()
                if value
            }
        )
        if not kyc_payload:
            raise MobileIdProviderUnavailableError(
                "Для сверки через Mobile ID не хватает данных профиля.",
                status_code=422,
            )
        request_token = jwe.encrypt(
            json.dumps(kyc_payload, ensure_ascii=False),
            enc_keys[0],
            algorithm=_jwe_algorithm_for_key(enc_keys[0]),
            encryption="A256GCM",
            kid=str(enc_keys[0].get("kid") or ""),
        )
        response = await self._request(
            "POST",
            _mobile_id_oidc_url("kyc-match-split"),
            mts_operation="kyc_match_split",
            mts_plaintext_content=kyc_payload,
            content=request_token,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/jwt",
            },
        )
        if response.status_code >= 400:
            raise _provider_error_from_response(response, operation="kyc_match_split")
        try:
            decrypted = jwe.decrypt(
                response.content,
                mobile_id_private_key_pem(settings.mobile_id_enc_kid),
            )
            decrypted_payload = dict(json.loads(decrypted.decode("utf-8")))
            logger.info(
                "%s response_plain operation=kyc_match_split payload=%s",
                _MTS_LOG_PREFIX,
                decrypted_payload,
            )
            return decrypted_payload
        except (JWTError, ValueError, TypeError, FileNotFoundError) as exc:
            raise MobileIdProviderUnavailableError(
                "Mobile ID прислал некорректное подтверждение. "
                "Попробуйте пройти верификацию заново.",
                status_code=502,
            ) from exc

    async def handle_notification(
        self,
        *,
        id_token: str,
        access_token: str,
        jwks_uri: str | None,
        phone_number: str | None,
        birthdate: date | None,
        family_name: str | None = None,
        given_name: str | None = None,
        middle_name: str | None = None,
    ) -> IdentityVerificationData:
        payload = await self._decode_id_token(
            id_token=id_token,
            access_token=access_token,
            jwks_uri=jwks_uri,
        )
        sub = str(payload.get("sub") or "")
        if not sub:
            raise MobileIdProviderUnavailableError(
                "Mobile ID прислал неполное подтверждение. "
                "Попробуйте пройти верификацию заново.",
                status_code=502,
            )
        birthdate_match = None
        kyc_request_fields = {
            "birthdate": birthdate,
            "family_name": family_name,
            "given_name": given_name,
            "middle_name": middle_name,
        }
        if any(value for value in kyc_request_fields.values()):
            kyc = await self._kyc_match_profile(
                access_token=access_token,
                jwks_uri=jwks_uri,
                birthdate=birthdate,
                family_name=family_name,
                given_name=given_name,
                middle_name=middle_name,
            )
            kyc_sub = str(kyc.get("sub") or "")
            if kyc_sub and kyc_sub != sub:
                raise MobileIdProviderUnavailableError(
                    "Mobile ID прислал некорректное подтверждение. "
                    "Попробуйте пройти верификацию заново.",
                    status_code=502,
                )
            failed_fields: list[str] = []
            for field, expected in kyc_request_fields.items():
                if not expected:
                    continue
                match_value = str(kyc.get(f"{field}_match") or "")
                if field == "birthdate":
                    birthdate_match = match_value
                if match_value != "Y":
                    failed_fields.append(field)
            if failed_fields:
                raise MobileIdProviderUnavailableError(
                    "Данные профиля не совпали с данными Mobile ID. "
                    "Проверьте ФИО и дату рождения в профиле.",
                    status_code=422,
                )
        return IdentityVerificationData(
            mobile_id_sub=sub,
            phone_number=phone_number,
            birthdate=birthdate,
            birthdate_match=birthdate_match,
            family_name=family_name,
            given_name=given_name,
            middle_name=middle_name,
        )


def get_mobile_id_provider() -> IdentityVerificationProvider:
    provider_name = settings.mobile_id_provider
    if not settings.mobile_id_enabled or provider_name == "local":
        return LocalMobileIdProvider()
    if provider_name == "eqid":
        from infrastructure.services.mobile_id.eqid import EqidMobileIdProvider

        return EqidMobileIdProvider()
    if provider_name == "mts":
        return MobileIdHttpProvider()
    raise MobileIdProviderUnavailableError(
        "Неизвестный провайдер верификации личности.",
        status_code=500,
    )
