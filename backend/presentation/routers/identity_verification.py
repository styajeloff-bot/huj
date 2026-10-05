from __future__ import annotations

import logging
from typing import Annotated, Any
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from application.commands.identity_verification import (
    HandleMobileIdNotificationCommand,
    HandleMobileIdSmsOtpNotificationCommand,
    StartIdentityVerificationCommand,
    SubmitIdentityVerificationSmsCodeCommand,
    handle_mobile_id_notification,
    handle_mobile_id_sms_otp_notification,
    handle_start_identity_verification,
    handle_submit_identity_verification_sms_code,
)
from application.errors import ServiceError, domain_to_http
from application.queries.identity_verification import (
    GetMyIdentityVerificationQuery,
    handle_get_my_identity_verification,
)
from domain.errors import DomainError
from domain.services.identity_verification import IdentityVerificationProvider
from infrastructure.cache.mobile_id_diagnostics import (
    MobileIdDiagnosticsRateLimitExceededError,
    MobileIdDiagnosticsRateLimitUnavailableError,
    enforce_mobile_id_diagnostics_rate_limit,
)
from infrastructure.database import get_db
from infrastructure.services.mobile_id.client import (
    MobileIdHttpProvider,
    MobileIdProviderUnavailableError,
)
from infrastructure.settings import settings
from presentation.dependencies.auth import get_current_user, require_roles
from presentation.schemas.identity_verification import (
    IdentityVerificationAttemptResponse,
    IdentityVerificationStatusResponse,
    MobileIdCallbackResponse,
    MobileIdDiagnosticsRequest,
    MobileIdDiagnosticsResponse,
    MobileIdNotificationRequest,
    MobileIdSmsOtpNotificationRequest,
    StartIdentityVerificationRequest,
    SubmitSmsCodeRequest,
)

router = APIRouter()
logger = logging.getLogger("carcraft-backend")

_MTS_LOG_PREFIX = "[ MTS ]"
_MOBILE_ID_INVALID_CALLBACK_DETAIL = "Invalid Mobile ID callback payload"
_MOBILE_ID_CALLBACK_SENSITIVE_KEYS = frozenset(
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


def _http(exc: ServiceError | DomainError) -> HTTPException:
    if isinstance(exc, DomainError):
        exc = domain_to_http(exc)
    return HTTPException(status_code=exc.status_code, detail=str(exc))


def _mobile_id_callback_authorized(authorization: str | None) -> bool:
    expected = settings.mobile_id_notification_token.strip()
    if not expected:
        return True
    scheme, _, token = (authorization or "").partition(" ")
    return scheme.lower() == "bearer" and token == expected


def _mobile_id_callback_payload_type(body: dict[str, Any]) -> str:
    if "smsotp_endpoint" in body:
        return "sms_otp"
    if "id_token" in body and "access_token" in body:
        return "notification"
    if "error" in body or "error_description" in body:
        return "error"
    return "unknown"


def _mobile_id_callback_url_host(body: dict[str, Any], key: str) -> str | None:
    endpoint = body.get(key)
    if not isinstance(endpoint, str) or not endpoint:
        return None
    parsed = urlsplit(endpoint)
    return parsed.netloc or None


def _mobile_id_callback_url_value(body: dict[str, Any], key: str) -> str | None:
    value = body.get(key)
    return value if isinstance(value, str) and value else None


def _mobile_id_callback_endpoint_host(body: dict[str, Any]) -> str | None:
    return _mobile_id_callback_url_host(body, "smsotp_endpoint")


def _mobile_id_callback_jwks_uri(body: dict[str, Any]) -> str | None:
    return _mobile_id_callback_url_value(body, "jwks_uri")


def _mobile_id_callback_jwks_uri_host(body: dict[str, Any]) -> str | None:
    return _mobile_id_callback_url_host(body, "jwks_uri")


def _mobile_id_callback_client_host(request: Request) -> str | None:
    if request.client is None:
        return None
    return request.client.host


def _mobile_id_callback_log_value(value: Any) -> Any:
    if isinstance(value, dict):
        return _mobile_id_callback_payload_for_log(value)
    if isinstance(value, list):
        return [_mobile_id_callback_log_value(item) for item in value]
    return value


def _mobile_id_callback_payload_for_log(body: dict[str, Any]) -> dict[str, Any]:
    return {
        str(key): (
            "***"
            if str(key).lower() in _MOBILE_ID_CALLBACK_SENSITIVE_KEYS
            else _mobile_id_callback_log_value(value)
        )
        for key, value in body.items()
    }


def _mobile_id_validation_error_for_log(exc: ValidationError) -> dict[str, Any]:
    return {
        "error_count": exc.error_count(),
        "errors": [
            {"type": error.get("type"), "loc": error.get("loc")}
            for error in exc.errors(include_input=False, include_url=False)
        ],
    }


def get_mobile_id_diagnostics_provider() -> IdentityVerificationProvider:
    return MobileIdHttpProvider()


def _mask_mobile_id_diagnostics_phone(phone: str) -> str:
    digits = "".join(ch for ch in phone if ch.isdigit())
    suffix = digits[-3:] if len(digits) >= 3 else digits
    return f"+7 *** *** *{suffix}" if suffix else "***"


async def _handle_mobile_id_sms_otp_callback(
    *,
    body: MobileIdSmsOtpNotificationRequest,
    session: AsyncSession,
) -> JSONResponse:
    try:
        result = await handle_mobile_id_sms_otp_notification(
            HandleMobileIdSmsOtpNotificationCommand(
                correlation_id=body.correlation_id,
                auth_req_id=body.auth_req_id,
                smsotp_endpoint=body.smsotp_endpoint,
                leading_kyc_match=body.leading_kyc_match,
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        logger.info(
            "%s callback ignored operation=mobile_id_webhook payload_type=sms_otp "
            "correlation_id=%s reason=handler_error error_type=%s error=%s",
            _MTS_LOG_PREFIX,
            body.correlation_id,
            type(exc).__name__,
            str(exc),
        )
        return JSONResponse(
            content=jsonable_encoder(
                {"id": None, "status": "ignored", "detail": str(exc)}
            )
        )
    await session.commit()
    logger.info(
        "%s callback processed operation=mobile_id_webhook payload_type=sms_otp "
        "correlation_id=%s id=%s status=%s",
        _MTS_LOG_PREFIX,
        body.correlation_id,
        result["id"],
        result["status"],
    )
    return JSONResponse(
        content=jsonable_encoder({"id": result["id"], "status": result["status"]})
    )


async def _handle_mobile_id_notification_callback(
    *,
    body: MobileIdNotificationRequest,
    session: AsyncSession,
) -> JSONResponse:
    try:
        result = await handle_mobile_id_notification(
            HandleMobileIdNotificationCommand(
                correlation_id=body.correlation_id,
                id_token=body.id_token,
                access_token=body.access_token,
                jwks_uri=body.jwks_uri,
                leading_kyc_match=body.leading_kyc_match,
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        logger.info(
            "%s callback ignored operation=mobile_id_webhook payload_type=notification "
            "correlation_id=%s reason=handler_error error_type=%s error=%s",
            _MTS_LOG_PREFIX,
            body.correlation_id,
            type(exc).__name__,
            str(exc),
        )
        return JSONResponse(
            content=jsonable_encoder(
                {"id": None, "status": "ignored", "detail": str(exc)}
            )
        )
    await session.commit()
    logger.info(
        "%s callback processed operation=mobile_id_webhook payload_type=notification "
        "correlation_id=%s id=%s status=%s",
        _MTS_LOG_PREFIX,
        body.correlation_id,
        result["id"],
        result["status"],
    )
    return JSONResponse(
        content=jsonable_encoder({"id": result["id"], "status": result["status"]})
    )


@router.get(
    "/users/me/identity-verification",
    response_model=IdentityVerificationStatusResponse,
    summary="Статус верификации текущего пользователя",
    description=(
        "Возвращает подтверждённое состояние Mobile ID и последнюю активную "
        "попытку текущего пользователя. Требует JWT."
    ),
)
async def get_my_identity_verification(
    user: Annotated[dict[str, Any], Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    try:
        result = await handle_get_my_identity_verification(
            GetMyIdentityVerificationQuery(user_id=user["id"]),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc) from exc
    return JSONResponse(content=jsonable_encoder(result))


@router.post(
    "/users/me/identity-verifications",
    response_model=IdentityVerificationAttemptResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Начать верификацию через Mobile ID",
    description=(
        "Создаёт попытку Mobile ID для текущего пользователя и переводит её "
        "в SMS-шаг. В локальном режиме без включённого Mobile ID использует "
        "безопасный fake-провайдер без сетевых вызовов."
    ),
)
async def start_my_identity_verification(
    body: StartIdentityVerificationRequest,
    user: Annotated[dict[str, Any], Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    try:
        result = await handle_start_identity_verification(
            StartIdentityVerificationCommand(
                user_id=user["id"],
                birth_date=body.birth_date,
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc) from exc
    await session.commit()
    location = f"/api/v1/users/me/identity-verifications/{result['verification_id']}"
    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content=jsonable_encoder(result),
        headers={"Location": location},
    )


@router.post(
    "/users/me/identity-verifications/{verification_id}/sms-code",
    response_model=IdentityVerificationAttemptResponse,
    summary="Подтвердить SMS-код Mobile ID",
    description=(
        "Передаёт SMS-код в провайдерский слой Mobile ID и возвращает "
        "текущее состояние попытки. Коммит выполняется на уровне роутера."
    ),
)
async def submit_my_identity_verification_sms_code(
    body: SubmitSmsCodeRequest,
    verification_id: Annotated[UUID, Path()],
    user: Annotated[dict[str, Any], Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    try:
        result = await handle_submit_identity_verification_sms_code(
            SubmitIdentityVerificationSmsCodeCommand(
                user_id=user["id"],
                verification_id=verification_id,
                code=body.code,
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc) from exc
    await session.commit()
    return JSONResponse(content=jsonable_encoder(result))


@router.post(
    "/admin/mobile-id/diagnostics/si-authorize",
    response_model=MobileIdDiagnosticsResponse,
    summary="[admin] Диагностика SI authorize Mobile ID",
    description=(
        "Отправляет реальный Mobile ID SI authorize запрос для диагностики "
        "интеграции MTS. Доступно только сотрудникам CarCraft. Не создаёт "
        "попытку user_identity_verifications и не изменяет профиль клиента."
    ),
)
async def start_admin_mobile_id_diagnostics(
    body: MobileIdDiagnosticsRequest,
    admin: Annotated[dict[str, Any], Depends(require_roles("carcraft_employee"))],
    provider: Annotated[
        IdentityVerificationProvider,
        Depends(get_mobile_id_diagnostics_provider),
    ],
) -> JSONResponse:
    correlation_id = uuid4()
    phone_masked = _mask_mobile_id_diagnostics_phone(body.phone)
    try:
        await enforce_mobile_id_diagnostics_rate_limit(admin["id"])
    except MobileIdDiagnosticsRateLimitExceededError as exc:
        raise HTTPException(
            status_code=429,
            detail=(
                "Слишком много диагностических запросов Mobile ID. "
                "Попробуйте позже."
            ),
        ) from exc
    except MobileIdDiagnosticsRateLimitUnavailableError as exc:
        raise HTTPException(
            status_code=503,
            detail="Диагностика Mobile ID временно недоступна. Попробуйте позже.",
        ) from exc
    logger.info(
        "%s diagnostics request operation=si_authorize actor_id=%s "
        "correlation_id=%s phone_masked=%s",
        _MTS_LOG_PREFIX,
        admin["id"],
        correlation_id,
        phone_masked,
    )
    try:
        started = await provider.start(
            user_id=admin["id"],
            phone_number=body.phone,
            birthdate=body.birth_date,
            correlation_id=correlation_id,
        )
    except MobileIdProviderUnavailableError as exc:
        logger.info(
            "%s diagnostics response operation=si_authorize actor_id=%s "
            "correlation_id=%s phone_masked=%s status=failed status_code=%s",
            _MTS_LOG_PREFIX,
            admin["id"],
            correlation_id,
            phone_masked,
            exc.status_code,
        )
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    logger.info(
        "%s diagnostics response operation=si_authorize actor_id=%s "
        "correlation_id=%s phone_masked=%s status=sms_requested",
        _MTS_LOG_PREFIX,
        admin["id"],
        correlation_id,
        started.phone_masked,
    )
    return JSONResponse(
        content=jsonable_encoder(
            {
                "correlation_id": correlation_id,
                "status": "sms_requested",
                "phone_masked": started.phone_masked,
                "expires_at": started.expires_at,
                "provider": "mobile_id",
            }
        )
    )


@router.post(
    "/notifications/webhook/mobileid",
    response_model=MobileIdCallbackResponse,
    summary="Mobile ID SMS OTP webhook",
    description=(
        "Публичный согласованный webhook от Mobile ID для SMS OTP callback. "
        "JWT не требуется."
    ),
)
async def mobile_id_sms_otp_webhook(
    request: Request,
    body: dict[str, Any],
    session: Annotated[AsyncSession, Depends(get_db)],
    authorization: Annotated[str | None, Header()] = None,
) -> JSONResponse:
    payload_type = _mobile_id_callback_payload_type(body)
    correlation_id = body.get("correlation_id")
    authorized = _mobile_id_callback_authorized(authorization)
    logger.info(
        "%s callback received operation=mobile_id_webhook path=%s client=%s "
        "payload_type=%s correlation_id=%s authorized=%s payload=%s "
        "smsotp_endpoint_host=%s jwks_uri=%s jwks_uri_host=%s",
        _MTS_LOG_PREFIX,
        request.url.path,
        _mobile_id_callback_client_host(request),
        payload_type,
        correlation_id,
        authorized,
        _mobile_id_callback_payload_for_log(body),
        _mobile_id_callback_endpoint_host(body),
        _mobile_id_callback_jwks_uri(body),
        _mobile_id_callback_jwks_uri_host(body),
    )
    if not authorized:
        logger.info(
            "%s callback ignored operation=mobile_id_webhook payload_type=%s "
            "correlation_id=%s reason=unauthorized",
            _MTS_LOG_PREFIX,
            payload_type,
            correlation_id,
        )
        return JSONResponse(content={"id": None, "status": "ignored"})
    try:
        if "smsotp_endpoint" in body:
            sms_body = MobileIdSmsOtpNotificationRequest.model_validate(body)
            return await _handle_mobile_id_sms_otp_callback(
                body=sms_body,
                session=session,
            )
    except ValidationError as exc:
        logger.info(
            "%s callback ignored operation=mobile_id_webhook payload_type=%s "
            "correlation_id=%s reason=validation_error error=%s payload=%s",
            _MTS_LOG_PREFIX,
            payload_type,
            correlation_id,
            _mobile_id_validation_error_for_log(exc),
            _mobile_id_callback_payload_for_log(body),
        )
        return JSONResponse(
            content=jsonable_encoder(
                {
                    "id": None,
                    "status": "ignored",
                    "detail": _MOBILE_ID_INVALID_CALLBACK_DETAIL,
                }
            )
        )
    logger.info(
        "%s callback ignored operation=mobile_id_webhook payload_type=%s "
        "correlation_id=%s reason=unsupported_payload payload=%s",
        _MTS_LOG_PREFIX,
        payload_type,
        correlation_id,
        _mobile_id_callback_payload_for_log(body),
    )
    return JSONResponse(
        content={
            "id": None,
            "status": "ignored",
            "detail": "Unsupported Mobile ID webhook payload",
        }
    )


@router.post(
    "/notifications/webhook/mobileid-final",
    response_model=MobileIdCallbackResponse,
    summary="Mobile ID final notification webhook",
    description=(
        "Публичный согласованный webhook от Mobile ID для финального статуса "
        "верификации. JWT не требуется."
    ),
)
async def mobile_id_final_webhook(
    request: Request,
    body: dict[str, Any],
    session: Annotated[AsyncSession, Depends(get_db)],
    authorization: Annotated[str | None, Header()] = None,
) -> JSONResponse:
    payload_type = _mobile_id_callback_payload_type(body)
    correlation_id = body.get("correlation_id")
    authorized = _mobile_id_callback_authorized(authorization)
    logger.info(
        "%s callback received operation=mobile_id_webhook path=%s client=%s "
        "payload_type=%s correlation_id=%s authorized=%s payload=%s "
        "smsotp_endpoint_host=%s jwks_uri=%s jwks_uri_host=%s",
        _MTS_LOG_PREFIX,
        request.url.path,
        _mobile_id_callback_client_host(request),
        payload_type,
        correlation_id,
        authorized,
        _mobile_id_callback_payload_for_log(body),
        _mobile_id_callback_endpoint_host(body),
        _mobile_id_callback_jwks_uri(body),
        _mobile_id_callback_jwks_uri_host(body),
    )
    if not authorized:
        logger.info(
            "%s callback ignored operation=mobile_id_webhook payload_type=%s "
            "correlation_id=%s reason=unauthorized",
            _MTS_LOG_PREFIX,
            payload_type,
            correlation_id,
        )
        return JSONResponse(content={"id": None, "status": "ignored"})
    try:
        if "id_token" in body and "access_token" in body:
            notification_body = MobileIdNotificationRequest.model_validate(body)
            return await _handle_mobile_id_notification_callback(
                body=notification_body,
                session=session,
            )
    except ValidationError as exc:
        logger.info(
            "%s callback ignored operation=mobile_id_webhook payload_type=%s "
            "correlation_id=%s reason=validation_error error=%s payload=%s",
            _MTS_LOG_PREFIX,
            payload_type,
            correlation_id,
            _mobile_id_validation_error_for_log(exc),
            _mobile_id_callback_payload_for_log(body),
        )
        return JSONResponse(
            content=jsonable_encoder(
                {
                    "id": None,
                    "status": "ignored",
                    "detail": _MOBILE_ID_INVALID_CALLBACK_DETAIL,
                }
            )
        )
    logger.info(
        "%s callback ignored operation=mobile_id_webhook payload_type=%s "
        "correlation_id=%s reason=unsupported_payload payload=%s",
        _MTS_LOG_PREFIX,
        payload_type,
        correlation_id,
        _mobile_id_callback_payload_for_log(body),
    )
    return JSONResponse(
        content={
            "id": None,
            "status": "ignored",
            "detail": "Unsupported Mobile ID webhook payload",
        }
    )
