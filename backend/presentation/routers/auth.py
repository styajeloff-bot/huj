"""Auth routes — login, register, verify-phone, resend-code, refresh, me, logout."""
import logging
import secrets
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Cookie, Depends, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from application.commands.auth import (
    LoginCommand,
    MagicLinkConsumeCommand,
    RefreshTokenCommand,
    RegisterCommand,
    ResendCodeCommand,
    VerifyPhoneCommand,
    handle_login,
    handle_logout,
    handle_magic_consume,
    handle_refresh_token,
    handle_register,
    handle_resend_code,
    handle_verify_phone,
)
from application.commands.mfa import (
    CompleteMfaSetupCommand,
    DisableMfaCommand,
    GetMfaStatusQuery,
    InitMfaSetupCommand,
    MfaSetupRequired,
    MfaStepUpRequired,
    RegenerateBackupCodesCommand,
    SetupMfaCommand,
    VerifyMfaLoginCommand,
    VerifyMfaSetupCommand,
    handle_complete_mfa_setup,
    handle_disable_mfa,
    handle_get_mfa_status,
    handle_init_mfa_setup,
    handle_regenerate_backup_codes,
    handle_setup_mfa,
    handle_verify_mfa_login,
    handle_verify_mfa_setup,
)
from application.commands.privacy import (
    EraseMyAccountCommand,
    handle_erase_my_account,
)
from application.errors import ServiceError, domain_to_http
from domain.errors import DomainError
from infrastructure.auth import decode_access_token, decode_refresh_token
from infrastructure.cache.token_denylist import AuthDenylistError, revoke
from infrastructure.database import get_db
from infrastructure.messaging import auth_events
from infrastructure.settings import settings
from presentation.dependencies.auth import (
    get_current_user,
    get_current_user_optional,
    get_current_user_with_db,
)
from presentation.dependencies.rate_limit import (
    rate_limit_login,
    rate_limit_refresh,
    rate_limit_register,
    rate_limit_resend,
    rate_limit_verify,
)
from presentation.dependencies.request_context import RequestContextDep
from presentation.schemas.auth import (
    AuthResponse,
    LoginRequest,
    MagicConsumeRequest,
    MeResponse,
    MessageResponse,
    MfaBackupCodesResponse,
    MfaCompleteRequest,
    MfaCompleteResponse,
    MfaDisableRequest,
    MfaInitRequest,
    MfaSetupRequiredResponse,
    MfaSetupResponse,
    MfaStatusResponse,
    MfaStepUpRequiredResponse,
    MfaVerifyLoginRequest,
    RegisterRequest,
    RegistrationPendingResponse,
    ResendCodeRequest,
    VerifyPhoneRequest,
)

router = APIRouter()
logger = logging.getLogger("carcraft-backend")

# Refresh token only needs to travel to /api/v1/auth/refresh & /logout —
# scoping the cookie narrows its exposure and disables it for every other
# request (Path attribute), which is a hard lock against XSS exfiltration
# chained with cookie theft.
_REFRESH_COOKIE_PATH = "/api/v1/auth"


def _http(exc: ServiceError | DomainError) -> HTTPException:
    if isinstance(exc, DomainError):
        exc = domain_to_http(exc)
    return HTTPException(status_code=exc.status_code, detail=str(exc))


def _set_auth_cookies(response: JSONResponse, access_token: str, refresh_token: str) -> None:
    access_max_age = settings.access_token_expiry_minutes * 60
    refresh_max_age = settings.refresh_token_expiry_days * 24 * 60 * 60
    response.set_cookie(
        key="accessToken",
        value=access_token,
        httponly=True,
        secure=settings.cookie_secure,
        max_age=access_max_age,
        samesite=settings.cookie_samesite,
        path="/",
    )
    response.set_cookie(
        key="refreshToken",
        value=refresh_token,
        httponly=True,
        secure=settings.cookie_secure,
        max_age=refresh_max_age,
        samesite=settings.cookie_samesite,
        path=_REFRESH_COOKIE_PATH,
    )
    if settings.csrf_enabled:
        response.set_cookie(
            key=settings.csrf_cookie_name,
            value=secrets.token_urlsafe(32),
            httponly=False,  # JS reads this to echo into X-CSRF-Token header
            secure=settings.cookie_secure,
            max_age=access_max_age,
            samesite=settings.cookie_samesite,
            path="/",
        )


async def _revoke_access_cookie(access_token: str | None) -> None:
    """Put the access-token's jti on the denylist. Safe to call with junk."""
    if not access_token:
        return
    try:
        payload = decode_access_token(access_token)
    except JWTError:
        return
    jti = payload.get("jti")
    if not jti:
        return
    try:
        await revoke(jti, exp=payload.get("exp"))
    except AuthDenylistError as exc:
        logger.error("Access-token revocation failed: %s", exc)
        raise
    auth_events.emit(
        auth_events.AUTH_REVOKED,
        user_id=payload.get("userId"),
        jti=jti,
    )


def _decode_refresh_token_or_401(refresh_token: str) -> dict[str, Any]:
    try:
        return decode_refresh_token(refresh_token)
    except JWTError as exc:
        if "expired" in str(exc).lower():
            raise HTTPException(
                status_code=401,
                detail={"error": "Refresh token истёк", "code": "REFRESH_TOKEN_EXPIRED"},
            ) from exc
        raise HTTPException(
            status_code=401,
            detail={"error": "Недействительный refresh token", "code": "REFRESH_TOKEN_INVALID"},
        ) from exc


def _uuid_claim(value: Any) -> UUID | None:
    if isinstance(value, UUID):
        return value
    if isinstance(value, str):
        try:
            return UUID(value)
        except ValueError:
            return None
    return None


@router.post(
    "/login",
    summary="Войти по номеру телефона",
    description=(
        "Отправляет SMS-код на указанный номер. "
        "Если пользователь не зарегистрирован — возвращает 404 с `requiresRegistration: true`. "
        "Если код уже отправлен (кулдаун 60 с) — возвращает 403 с `codeAlreadySent: true`. "
        "При успехе — 200 с `requiresVerification: true`."
    ),
    dependencies=[rate_limit_login],
)
async def login(
    body: LoginRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    try:
        result = await handle_login(LoginCommand(phone=body.phone), session)
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    await session.commit()

    if result.user_exists:
        if result.code_already_sent:
            return JSONResponse(
                status_code=403,
                content={
                    "error": "Код подтверждения уже был отправлен",
                    "requiresVerification": True,
                    "phone": result.phone,
                    "codeAlreadySent": True,
                    "message": result.message,
                },
            )
        return JSONResponse(
            status_code=200,
            content={
                "requiresVerification": True,
                "phone": result.phone,
                "message": result.message,
            },
        )

    # User not found — needs registration
    if result.code_already_sent:
        return JSONResponse(
            status_code=403,
            content={
                "error": "Пользователь не найден",
                "requiresRegistration": True,
                "phone": result.phone,
                "codeAlreadySent": True,
                "message": result.message,
            },
        )
    return JSONResponse(
        status_code=404,
        content={
            "error": "Пользователь не найден",
            "requiresRegistration": True,
            "phone": result.phone,
            "message": result.message,
        },
    )

@router.post(
    "/register",
    response_model=AuthResponse | RegistrationPendingResponse | MfaStepUpRequiredResponse | MfaSetupRequiredResponse,
    status_code=201,
    summary="Зарегистрировать пользователя",
    description=(
        "Создаёт пользователя и привязывает выбранные компании из frontend payload. "
        "Если передан корректный `code`, регистрация завершается сразу и "
        "устанавливает auth cookies. Иначе создаёт пользователя и отправляет "
        "код подтверждения на телефон."
    ),
    dependencies=[rate_limit_register],
)
async def register(
    body: RegisterRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
    request_context: RequestContextDep,
) -> JSONResponse:
    try:
        result = await handle_register(
            RegisterCommand(
                phone=body.phone,
                email=body.email,
                name=body.name,
                companies=[item.model_dump() for item in body.companies or []],
                code=body.code,
                request_context=request_context,
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    await session.commit()

    if isinstance(result, MfaStepUpRequired):
        return JSONResponse(
            content={
                "mfaRequired": True,
                "mfaToken": result.mfa_token,
                "message": "Требуется код второго фактора",
            }
        )

    if isinstance(result, MfaSetupRequired):
        return JSONResponse(
            content={
                "mfaSetupRequired": True,
                "setupToken": result.setup_token,
                "message": (
                    "Для вашей роли требуется настройка двухфакторной "
                    "аутентификации"
                ),
            }
        )

    if result.verified and result.user and result.tokens:
        resp = JSONResponse(
            status_code=201,
            content={"message": result.message, "user": jsonable_encoder(result.user)},
        )
        _set_auth_cookies(resp, result.tokens.access_token, result.tokens.refresh_token)
        return resp

    return JSONResponse(
        status_code=201,
        content={
            "message": result.message,
            "phone": result.phone,
            "requiresVerification": True,
        },
    )


@router.post(
    "/verify-phone",
    response_model=AuthResponse | MfaStepUpRequiredResponse | MfaSetupRequiredResponse,
    summary="Подтвердить номер телефона",
    description=(
        "Проверяет SMS-код и верифицирует пользователя. "
        "При успехе и отключённой MFA устанавливает `accessToken` и "
        "`refreshToken` cookies и возвращает данные пользователя. "
        "Если у пользователя включена MFA — возвращает половинную сессию "
        "`{mfaRequired: true, mfaToken}` без установки cookies; завершить "
        "логин можно через `POST /auth/mfa/verify`. "
        "Для привилегированных ролей без MFA возвращает "
        "`{mfaSetupRequired: true, setupToken}`; завершить настройку — "
        "через `POST /auth/mfa/complete-setup`."
    ),
    dependencies=[rate_limit_verify],
)
async def verify_phone(
    body: VerifyPhoneRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
    request_context: RequestContextDep,
) -> JSONResponse:
    try:
        result = await handle_verify_phone(
            VerifyPhoneCommand(
                phone=body.phone,
                code=body.code,
                request_context=request_context,
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    await session.commit()

    if isinstance(result, MfaStepUpRequired):
        return JSONResponse(
            content={
                "mfaRequired": True,
                "mfaToken": result.mfa_token,
                "message": "Требуется код второго фактора",
            }
        )

    if isinstance(result, MfaSetupRequired):
        return JSONResponse(
            content={
                "mfaSetupRequired": True,
                "setupToken": result.setup_token,
                "message": (
                    "Для вашей роли требуется настройка двухфакторной "
                    "аутентификации"
                ),
            }
        )

    resp = JSONResponse(
        content={"message": "Телефон успешно подтверждён", "user": jsonable_encoder(result.user)}
    )
    _set_auth_cookies(resp, result.tokens.access_token, result.tokens.refresh_token)
    return resp


@router.post(
    "/magic/consume",
    response_model=AuthResponse,
    summary="Активация по одноразовой ссылке (passwordless)",
    description=(
        "Принимает одноразовый токен из SMS-ссылки вида "
        "`{public_url}/s/{token}`, активирует пользователя "
        "(`is_active=true`, `phone_verified=true`) и ставит "
        "`accessToken` / `refreshToken` cookies. "
        "410 Gone — ссылка недействительна, просрочена или уже использована."
    ),
)
async def magic_consume(
    body: MagicConsumeRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
    request_context: RequestContextDep,
) -> JSONResponse:
    try:
        result = await handle_magic_consume(
            MagicLinkConsumeCommand(token=body.token, ctx=request_context),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    await session.commit()

    resp = JSONResponse(
        content={"message": "Вход выполнен", "user": result.user}
    )
    _set_auth_cookies(resp, result.tokens.access_token, result.tokens.refresh_token)
    return resp


@router.post(
    "/resend-code",
    response_model=MessageResponse,
    summary="Повторно отправить SMS-код",
    description="Отправляет новый код подтверждения на указанный телефон. Требует существующего пользователя.",
    dependencies=[rate_limit_resend],
)
async def resend_code(
    body: ResendCodeRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    try:
        await handle_resend_code(ResendCodeCommand(phone=body.phone), session)
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    await session.commit()
    return JSONResponse(content={"message": "Новый код подтверждения отправлен"})


@router.post(
    "/refresh",
    response_model=MessageResponse,
    summary="Обновить токены",
    description=(
        "Проверяет `refreshToken` cookie и выдаёт новую пару токенов. "
        "Обновлённые tokens устанавливаются в cookies."
    ),
    dependencies=[rate_limit_refresh],
)
async def refresh(
    session: Annotated[AsyncSession, Depends(get_db)],
    refresh_token: Annotated[str | None, Cookie(alias="refreshToken")] = None,
    access_token: Annotated[str | None, Cookie(alias="accessToken")] = None,
) -> JSONResponse:
    if not refresh_token:
        raise HTTPException(
            status_code=401,
            detail={"error": "Refresh token не найден", "code": "REFRESH_TOKEN_MISSING"},
        )
    payload = _decode_refresh_token_or_401(refresh_token)
    user_id = _uuid_claim(payload.get("userId"))
    refresh_session_id = _uuid_claim(payload.get("sid"))
    if user_id is None or refresh_session_id is None:
        raise HTTPException(
            status_code=401,
            detail={"error": "Недействительный refresh token", "code": "REFRESH_TOKEN_INVALID"},
        )

    try:
        tokens = await handle_refresh_token(
            RefreshTokenCommand(
                user_id=user_id,
                refresh_token=refresh_token,
                refresh_session_id=refresh_session_id,
                role=payload.get("role"),
                company_id=payload.get("company_id"),
            ),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    await session.commit()

    # Revoke the previous access-token jti — otherwise it stays valid until
    # its natural exp, defeating the point of rotation.
    try:
        await _revoke_access_cookie(access_token)
    except AuthDenylistError as exc:
        raise HTTPException(
            status_code=500,
            detail={"error": "Не удалось отозвать старый токен", "code": "REVOCATION_FAILED"},
        ) from exc

    resp = JSONResponse(content={"message": "Токены обновлены"})
    _set_auth_cookies(resp, tokens.access_token, tokens.refresh_token)
    return resp


@router.get(
    "/me",
    response_model=MeResponse,
    summary="Текущий пользователь",
    description="Возвращает данные аутентифицированного пользователя из JWT-токена.",
)
async def me(
    user: Annotated[dict, Depends(get_current_user_with_db)],
) -> JSONResponse:
    return JSONResponse(content={"user": jsonable_encoder(user)})


@router.post(
    "/logout",
    response_model=MessageResponse,
    summary="Выйти",
    description="Сбрасывает cookies `accessToken` и `refreshToken`.",
)
async def logout(
    session: Annotated[AsyncSession, Depends(get_db)],
    refresh_token: Annotated[str | None, Cookie(alias="refreshToken")] = None,
    access_token: Annotated[str | None, Cookie(alias="accessToken")] = None,
) -> JSONResponse:
    if refresh_token:
        try:
            payload = _decode_refresh_token_or_401(refresh_token)
        except HTTPException:
            payload = None
        if payload is not None:
            sid = _uuid_claim(payload.get("sid"))
            if sid is not None:
                await handle_logout(sid, session)
                await session.commit()

    try:
        await _revoke_access_cookie(access_token)
    except AuthDenylistError as exc:
        raise HTTPException(
            status_code=500,
            detail={"error": "Не удалось завершить сессию", "code": "REVOCATION_FAILED"},
        ) from exc

    resp = JSONResponse(content={"message": "Выход выполнен успешно"})
    resp.delete_cookie("accessToken", path="/")
    resp.delete_cookie("refreshToken", path=_REFRESH_COOKIE_PATH)
    if settings.csrf_enabled:
        resp.delete_cookie(settings.csrf_cookie_name, path="/")
    return resp


# ---------------------------------------------------------------------------
# MFA endpoints (R8 — REST consolidation)
#
# Single resource ``/auth/mfa`` with method-based dispatch:
#   GET    — status projection
#   POST   — init setup (auth OR mandatory-setup token)
#   PUT    — complete setup (auth OR mandatory-setup token)
#   DELETE — disable (requires TOTP for protection)
# Plus two satellites that stay separate because their context differs
# from the managed-resource surface:
#   POST /auth/mfa/verify        — runtime step-up during login (pre-auth)
#   POST /auth/mfa/backup-codes  — regenerate the user's backup-code set
# ---------------------------------------------------------------------------


@router.get(
    "/mfa",
    response_model=MfaStatusResponse,
    summary="Статус MFA",
    description=(
        "Возвращает текущее состояние MFA пользователя: включена или нет, "
        "используемый метод и сколько backup-кодов осталось. Настройка "
        "(QR, код, активация) — через `POST`/`PUT /auth/mfa`."
    ),
)
async def mfa_status(
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[dict[str, Any], Depends(get_current_user)],
) -> JSONResponse:
    try:
        result = await handle_get_mfa_status(
            GetMfaStatusQuery(user_id=user["id"]), session
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    return JSONResponse(
        content={
            "enabled": result.enabled,
            "method": result.method,
            "hasBackupCodes": result.has_backup_codes,
            "backupCodesRemaining": result.backup_codes_remaining,
        }
    )


@router.post(
    "/mfa",
    response_model=MfaSetupResponse,
    summary="Начать настройку MFA",
    description=(
        "Генерирует TOTP-секрет и сохраняет его как pending. Возвращает "
        "секрет, `otpauth://` URL и QR-код (PNG в base64). Для обычного "
        "аутентифицированного пользователя — тело пустое. Для "
        "обязательной настройки из half-сессии (`/auth/verify-phone` "
        "вернул `mfaSetupRequired: true, setupToken`) — передать "
        "`{setupToken}`. Активация — через `PUT /auth/mfa`."
    ),
    dependencies=[rate_limit_verify],
)
async def mfa_init(
    session: Annotated[AsyncSession, Depends(get_db)],
    current: Annotated[
        dict[str, Any] | None, Depends(get_current_user_optional)
    ],
    body: MfaInitRequest | None = None,
) -> JSONResponse:
    setup_token = body.setup_token if body is not None else None
    try:
        if setup_token:
            result = await handle_init_mfa_setup(
                InitMfaSetupCommand(setup_token=setup_token), session
            )
        else:
            # Authenticated-user flow: mirror the former /mfa/setup
            # semantics — reject with 401 when no valid token is present.
            if current is None:
                raise HTTPException(
                    status_code=401,
                    detail={
                        "error": "Токен доступа не найден",
                        "code": "TOKEN_MISSING",
                    },
                )
            result = await handle_setup_mfa(
                SetupMfaCommand(user_id=current["id"]), session
            )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    await session.commit()
    return JSONResponse(
        content={
            "secret": result.secret,
            "otpauthUrl": result.otpauth_url,
            "qrPngBase64": result.qr_png_base64,
        }
    )


@router.put(
    "/mfa",
    response_model=MfaCompleteResponse,
    summary="Подтвердить настройку MFA",
    description=(
        "Принимает первый TOTP-код и активирует MFA. Для обычного "
        "пользователя возвращает `{message, backupCodes}`. Для "
        "mandatory-enrolment-потока (body содержит `setupToken`) "
        "дополнительно устанавливает auth-cookies и возвращает "
        "`{user, backupCodes}`. Показывать backup-коды клиенту "
        "единоразово — повторно они не выдаются, только через "
        "`POST /auth/mfa/backup-codes`."
    ),
    dependencies=[rate_limit_verify],
)
async def mfa_complete(
    body: MfaCompleteRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
    current: Annotated[
        dict[str, Any] | None, Depends(get_current_user_optional)
    ],
) -> JSONResponse:
    try:
        if body.setup_token:
            complete = await handle_complete_mfa_setup(
                CompleteMfaSetupCommand(
                    setup_token=body.setup_token, code=body.code
                ),
                session,
            )
            await session.commit()
            resp = JSONResponse(
                content={
                    "user": complete.user,
                    "backupCodes": complete.backup_codes,
                }
            )
            _set_auth_cookies(
                resp,
                complete.tokens.access_token,
                complete.tokens.refresh_token,
            )
            return resp

        if current is None:
            raise HTTPException(
                status_code=401,
                detail={
                    "error": "Токен доступа не найден",
                    "code": "TOKEN_MISSING",
                },
            )
        activation = await handle_verify_mfa_setup(
            VerifyMfaSetupCommand(user_id=current["id"], code=body.code),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    await session.commit()
    return JSONResponse(
        content={
            "message": "MFA включена",
            "backupCodes": activation.backup_codes,
        }
    )


@router.delete(
    "/mfa",
    response_model=MessageResponse,
    summary="Отключить MFA",
    description=(
        "Требует тело `{code}` с валидным текущим TOTP-кодом как "
        "step-up подтверждение. При успехе очищает все MFA-артефакты "
        "пользователя (секрет, pending-секрет, backup-коды)."
    ),
)
async def mfa_delete(
    body: MfaDisableRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[dict[str, Any], Depends(get_current_user)],
) -> JSONResponse:
    try:
        await handle_disable_mfa(
            DisableMfaCommand(user_id=user["id"], code=body.code), session
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    await session.commit()
    return JSONResponse(content={"message": "MFA отключена"})


@router.post(
    "/mfa/verify",
    response_model=AuthResponse,
    summary="Завершить вход через MFA",
    description=(
        "Runtime-verify: принимает `mfaToken` из `/auth/verify-phone` и "
        "TOTP-код (или одноразовый backup code). При успехе устанавливает "
        "auth cookies и возвращает данные пользователя. Контекст — "
        "half-session (пользователь ещё не полностью авторизован), "
        "поэтому ручка оставлена отдельно от REST-resource `/auth/mfa`."
    ),
    dependencies=[rate_limit_verify],
)
async def mfa_verify(
    body: MfaVerifyLoginRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    try:
        result = await handle_verify_mfa_login(
            VerifyMfaLoginCommand(mfa_token=body.mfa_token, code=body.code),
            session,
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    await session.commit()

    resp = JSONResponse(
        content={"message": "MFA подтверждена", "user": result.user}
    )
    _set_auth_cookies(resp, result.tokens.access_token, result.tokens.refresh_token)
    return resp


@router.post(
    "/mfa/backup-codes",
    response_model=MfaBackupCodesResponse,
    summary="Перегенерировать backup-коды",
    description=(
        "Генерирует новый набор одноразовых backup-кодов, инвалидируя "
        "предыдущие. Показывать пользователю один раз. Требует "
        "включённую MFA (иначе 400) и аутентифицированного пользователя."
    ),
)
async def mfa_regenerate_backup_codes(
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[dict[str, Any], Depends(get_current_user)],
) -> JSONResponse:
    try:
        result = await handle_regenerate_backup_codes(
            RegenerateBackupCodesCommand(user_id=user["id"]), session
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    await session.commit()
    return JSONResponse(content={"backupCodes": result.backup_codes})


# ---------------------------------------------------------------------------
# GDPR self-service erasure (BE-5)
# ---------------------------------------------------------------------------


@router.delete(
    "/me",
    response_model=MessageResponse,
    summary="Удалить мою учётную запись (анонимизация)",
    description=(
        "GDPR art. 17 / 152-ФЗ ст. 14. Необратимо анонимизирует профиль: "
        "удаляются активные сессии, обнуляются PII-поля, записи аудита "
        "по этому пользователю маскируются. Строка в БД остаётся ради "
        "целостности внешних ссылок (заказы, отчётность)."
    ),
)
async def delete_me(
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[dict[str, Any], Depends(get_current_user)],
    access_token: Annotated[str | None, Cookie(alias="accessToken")] = None,
) -> JSONResponse:
    try:
        await handle_erase_my_account(
            EraseMyAccountCommand(user_id=user["id"]), session
        )
    except (ServiceError, DomainError) as exc:
        raise _http(exc)
    await session.commit()

    # Denylist the current access token so it can't be used post-anonymization.
    # If Redis is down we still succeed — the anonymization already committed,
    # ``is_active=False`` plus session wipe render the token useless anyway.
    try:
        await _revoke_access_cookie(access_token)
    except AuthDenylistError:
        logger.warning("Denylist write failed during /auth/me erasure")

    resp = JSONResponse(content={"message": "Учётная запись удалена"})
    resp.delete_cookie("accessToken", path="/")
    resp.delete_cookie("refreshToken", path=_REFRESH_COOKIE_PATH)
    if settings.csrf_enabled:
        resp.delete_cookie(settings.csrf_cookie_name, path="/")
    return resp
