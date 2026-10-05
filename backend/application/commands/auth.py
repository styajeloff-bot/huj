"""Auth commands and handlers."""
from __future__ import annotations

import asyncio
import hashlib
import logging
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any, cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.errors import ServiceError
from domain.errors import (
    CompanyLookupUnavailableError,
    InvalidVerificationCodeError,
    UserAlreadyExistsError,
    UserDeactivatedError,
    UserNotFoundError,
)
from domain.services.mfa_policy import is_mfa_required
from domain.services.scopes import roles_to_scopes
from infrastructure.auth import generate_tokens, hash_refresh_token
from infrastructure.cache import phone_lockout
from infrastructure.messaging import auth_events
from infrastructure.repositories import auth_repository as repo
from infrastructure.repositories import company_registration_repository as company_repo
from infrastructure.repositories import employees_repository
from infrastructure.repositories import magic_link_repository as magic_link_repo
from infrastructure.repositories.auth_repository import UserDict
from infrastructure.repositories.company_registration_repository import CompanyPayload
from infrastructure.services.company_lookup import get_company_lookup_provider
from infrastructure.services.sms import (
    get_verification_code,
    is_test_phone,
    send_verification_sms,
)
from infrastructure.settings import settings

if TYPE_CHECKING:
    from application.commands.mfa import MfaSetupRequired, MfaStepUpRequired

logger = logging.getLogger("carcraft-backend")

_CODE_EXPIRY_MINUTES = 10
_CODE_COOLDOWN_SECONDS = 60


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RequestContext:
    """Per-request metadata attached to a newly-minted session.

    Values are optional — the presentation dep extracts them best-effort
    from headers and falls back to ``None``. Repository/DB keep the nulls.
    """

    ip_address: str | None = None
    user_agent: str | None = None
    country_code: str | None = None


@dataclass
class LoginCommand:
    phone: str


@dataclass
class VerifyPhoneCommand:
    phone: str
    code: str
    request_context: RequestContext | None = None


@dataclass
class ResendCodeCommand:
    phone: str


@dataclass
class RefreshTokenCommand:
    user_id: UUID
    refresh_token: str
    refresh_session_id: UUID
    role: str | None
    company_id: UUID | None


@dataclass
class RegisterCommand:
    phone: str
    email: str | None
    name: str | None
    companies: list[dict[str, Any]]
    code: str | None = None
    request_context: RequestContext | None = None


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class LoginResult:
    user_exists: bool
    phone: str
    message: str
    code_already_sent: bool = False


@dataclass
class TokenPair:
    access_token: str
    refresh_token: str


@dataclass
class AuthResult:
    user: dict[str, Any]
    tokens: TokenPair


@dataclass
class RegisterResult:
    verified: bool
    phone: str
    message: str
    user: dict[str, Any] | None = None
    tokens: TokenPair | None = None


@dataclass
class MagicLinkConsumeCommand:
    """Passwordless activation via a one-shot SMS link."""

    token: str
    ctx: RequestContext = RequestContext()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _should_send_code(last_code_at: datetime | None, phone: str) -> bool:
    # Test phones never trigger real SMS — skip the cooldown entirely so
    # E2E tests can call /login repeatedly without hitting 403.
    if is_test_phone(phone):
        return True
    if last_code_at is None:
        return True
    if last_code_at.tzinfo is None:
        last_code_at = last_code_at.replace(tzinfo=UTC)
    elapsed = (datetime.now(UTC) - last_code_at).total_seconds()
    return elapsed >= _CODE_COOLDOWN_SECONDS


def _make_expires_at() -> datetime:
    return datetime.now(UTC) + timedelta(minutes=_CODE_EXPIRY_MINUTES)


def _make_placeholder_password_hash() -> str:
    return hashlib.sha256(secrets.token_bytes(32)).hexdigest()


async def _send_sms_background(phone: str, code: str, sms_type: str) -> None:
    """Fire-and-forget SMS send; logs errors without propagating."""
    try:
        await send_verification_sms(phone, code, sms_type)
    except Exception as exc:
        logger.error("Background SMS failed for %s: %s", phone, exc)


_sms_tasks: set[asyncio.Task[None]] = set()


def _fire_sms(phone: str, code: str, sms_type: str) -> None:
    """Schedule SMS send as a background asyncio task."""
    if not is_test_phone(phone):
        task = asyncio.create_task(_send_sms_background(phone, code, sms_type))
        _sms_tasks.add(task)
        task.add_done_callback(_sms_tasks.discard)


async def build_tokens(
    user: UserDict,
    session: AsyncSession,
    *,
    refresh_session_id: UUID | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    country_code: str | None = None,
) -> TokenPair:
    refresh_expires_at = datetime.now(UTC) + timedelta(days=settings.refresh_token_expiry_days)
    if refresh_session_id is None:
        user_session = await repo.create_user_session(
            session,
            user_id=user["id"],
            refresh_token_hash=hash_refresh_token(secrets.token_urlsafe(32)),
            expires_at=refresh_expires_at,
            ip_address=ip_address,
            user_agent=user_agent,
            country_code=country_code,
        )
        refresh_session_id = user_session["id"]
    access, refresh = generate_tokens(
        user["id"],
        user["role"],
        user["company_id"],
        refresh_session_id=refresh_session_id,
    )
    updated = await repo.update_user_session(
        session,
        session_id=refresh_session_id,
        refresh_token_hash=hash_refresh_token(refresh),
        expires_at=refresh_expires_at,
    )
    if updated is None:
        raise ServiceError("Не удалось сохранить refresh token", 500)
    return TokenPair(access_token=access, refresh_token=refresh)


def _format_user(user: UserDict) -> dict[str, Any]:
    return {
        "id": str(user["id"]) if user.get("id") else None,
        "phone": user["phone"],
        "email": user["email"],
        "name": user["name"],
        "role": user["role"],
        "scopes": roles_to_scopes(user.get("role")),
        "company_id": str(user["company_id"]) if user.get("company_id") else None,
    }


async def _format_user_with_permissions(
    session: AsyncSession,
    user: UserDict,
    company_id: UUID | None = None,
) -> dict[str, Any]:
    formatted = _format_user(user)
    user_id = user.get("id")
    companies = (
        await company_repo.list_user_companies(session, user_id)
        if user_id
        else []
    )
    available_companies = [
        {
            "id": str(c["id"]),
            "name": c["name"],
            "inn": c.get("inn"),
            "role": c.get("role") or "client",
            "position_id": str(c["position_id"]) if c.get("position_id") else None,
            "position_name": c.get("position_name"),
            "is_active": bool(c.get("is_active", True)),
        }
        for c in companies
    ]
    formatted["available_companies"] = available_companies

    active_company_id = company_id or user.get("company_id")
    if active_company_id is None and companies:
        active_company_id = companies[0]["id"]

    if active_company_id is None:
        formatted.update(
            {
                "active_role": user.get("role"),
                "active_company_id": None,
                "active_company_name": None,
                "position_id": None,
                "position_name": None,
            }
        )
        return formatted

    active_company = next(
        (c for c in companies if c["id"] == active_company_id), None
    )
    active_company_name = active_company.get("name") if active_company else None

    perms = await company_repo.get_company_permissions(
        session, user["id"], active_company_id
    )
    can_create_employees = False
    if user.get("role") == "carcraft_employee":
        can_create_employees = True
    elif active_company_id is not None:
        can_create_employees = await employees_repository.check_can_create_employees(
            session,
            actor_user_id=user["id"],
            actor_role=perms.get("role") or user.get("role") or "client",
            target_company_id=active_company_id,
        )
    effective_role = perms.get("role") or user.get("role")
    position_id = perms.get("position_id") or (
        active_company.get("position_id") if active_company else None
    )
    if position_id is not None:
        position_id = str(position_id)
    position_name = (
        active_company.get("position_name") if active_company else None
    )

    formatted.update(
        {
            "role": effective_role,
            "scopes": roles_to_scopes(effective_role),
            "company_id": str(active_company_id),
            "sub_role": perms.get("sub_role"),
            "can_view_applications": perms.get("can_view_applications"),
            "can_create_applications": perms.get("can_create_applications"),
            "can_create_employees": can_create_employees,
            "active_role": effective_role,
            "active_company_id": str(active_company_id),
            "active_company_name": active_company_name,
            "position_id": position_id,
            "position_name": position_name,
        }
    )
    return formatted


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

async def handle_login(cmd: LoginCommand, session: AsyncSession) -> LoginResult:
    user = await repo.find_user_by_phone(session, cmd.phone)
    last_code_at = await repo.get_last_code_created_at(session, cmd.phone)
    should_send = _should_send_code(last_code_at, cmd.phone)

    phone = user["phone"] if user else cmd.phone

    auth_events.emit(
        auth_events.LOGIN_REQUESTED,
        phone=phone,
        user_id=user["id"] if user else None,
        user_exists=bool(user),
        code_already_sent=not should_send,
    )

    if should_send:
        code = get_verification_code(cmd.phone)
        await repo.save_verification_code(session, cmd.phone, code, _make_expires_at())
        sms_type = 'login' if user else 'registration'
        _fire_sms(cmd.phone, code, sms_type)
        msg = "Код подтверждения отправлен на ваш телефон"
        return LoginResult(user_exists=bool(user), phone=phone, message=msg)

    msg = "Код подтверждения уже отправлен. Попробуйте через минуту."
    return LoginResult(
        user_exists=bool(user), phone=phone, message=msg, code_already_sent=True
    )


async def handle_verify_phone(
    cmd: VerifyPhoneCommand, session: AsyncSession
) -> AuthResult | MfaStepUpRequired | MfaSetupRequired:
    # Imported locally: application.commands.mfa imports from this module,
    # so a top-level import would create a circular dependency.
    from application.commands.mfa import build_mfa_setup_required, build_mfa_step_up

    if await phone_lockout.is_locked(cmd.phone):
        auth_events.emit(
            auth_events.PHONE_LOCKED,
            phone=cmd.phone,
            reason="too_many_failed_otp",
        )
        raise ServiceError(
            "Слишком много неудачных попыток. Попробуйте позже.", 429
        )

    if not await repo.verify_code(session, cmd.phone, cmd.code):
        failures = await phone_lockout.register_failure(cmd.phone)
        auth_events.emit(
            auth_events.LOGIN_FAILED,
            phone=cmd.phone,
            reason="invalid_code",
            failures=failures,
        )
        raise InvalidVerificationCodeError()

    user = await repo.find_user_by_phone(session, cmd.phone)
    if not user:
        raise UserNotFoundError()
    if not user["is_active"]:
        raise UserDeactivatedError()

    old_verified = user.get("phone_verified")
    user = await repo.set_phone_verified(session, cmd.phone)
    await repo.delete_codes(session, cmd.phone)
    await phone_lockout.clear(cmd.phone)
    from infrastructure.messaging.status_events import emit_client_status_changed
    emit_client_status_changed(
        user_id=user["id"],
        field="phone_verified",
        old_value=old_verified,
        new_value=True,
        changed_by=user["id"],
    )
    logger.info("Phone verified for user %s", cmd.phone)

    if user.get("mfa_enabled"):
        # Half-session: phone is verified but no tokens are issued until the
        # user submits the second factor via /auth/mfa/verify.
        auth_events.emit(
            auth_events.LOGIN_REQUESTED,
            user_id=user["id"],
            phone=user["phone"],
            role=user["role"],
            stage="mfa_pending",
        )
        return build_mfa_step_up(user["id"])

    if is_mfa_required(user["role"]):
        # Privileged role without MFA enrolment: force the setup flow.
        # A setup-purpose half-session token is returned instead of tokens;
        # the client must complete enrolment via /auth/mfa/complete-setup
        # before any access/refresh cookie is issued.
        auth_events.emit(
            auth_events.MFA_SETUP_REQUIRED,
            user_id=user["id"],
            phone=user["phone"],
            role=user["role"],
        )
        return build_mfa_setup_required(user["id"])

    active_cid, active_role = await employees_repository.get_active_company_and_role(
        session, user["id"], user["role"] or "client"
    )
    user_for_tokens = dict(user)
    if active_role and active_role != "client":
        user_for_tokens["role"] = active_role
    if active_cid and not user_for_tokens.get("company_id"):
        user_for_tokens["company_id"] = active_cid

    effective_role = user_for_tokens.get("role") or user["role"]
    auth_events.emit(
        auth_events.LOGIN_SUCCEEDED,
        user_id=user["id"],
        phone=user["phone"],
        role=effective_role,
    )
    ctx = cmd.request_context or RequestContext()
    return AuthResult(
        user=await _format_user_with_permissions(
            session, cast("UserDict", user_for_tokens), active_cid
        ),
        tokens=await build_tokens(
            cast("UserDict", user_for_tokens),
            session,
            ip_address=ctx.ip_address,
            user_agent=ctx.user_agent,
            country_code=ctx.country_code,
        ),
    )


async def handle_resend_code(cmd: ResendCodeCommand, session: AsyncSession) -> None:
    user = await repo.find_user_by_phone(session, cmd.phone)
    if not user:
        raise UserNotFoundError()

    code = get_verification_code(cmd.phone)
    await repo.save_verification_code(session, cmd.phone, code, _make_expires_at())

    _fire_sms(cmd.phone, code, 'login')

    logger.info("Resent verification code to %s", cmd.phone)


async def handle_refresh_token(cmd: RefreshTokenCommand, session: AsyncSession) -> TokenPair:
    user = await repo.find_user_by_id(session, cmd.user_id)
    if not user:
        raise UserNotFoundError()
    if not user["is_active"]:
        raise UserDeactivatedError()
    user_session = await repo.get_user_session(session, cmd.refresh_session_id)
    if user_session is None or user_session["user_id"] != cmd.user_id:
        raise ServiceError("Недействительный refresh token", 401)

    # --- BE-1: inactive-session timeout ---
    # Reject refresh if the session has been idle longer than the role-specific
    # cap, regardless of absolute expires_at. A stolen refresh token that sits
    # unused for days shouldn't be revivable just because the 7-day TTL hasn't
    # elapsed yet. Older rows may carry naive datetimes — normalise to UTC.
    last_used_at = user_session["last_used_at"] or user_session["created_at"]
    if last_used_at is not None:
        if last_used_at.tzinfo is None:
            last_used_at = last_used_at.replace(tzinfo=UTC)
        inactive_since = datetime.now(UTC) - last_used_at
        cap_hours = (
            settings.max_inactive_session_hours_employee
            if user["role"] == "carcraft_employee"
            else settings.max_inactive_session_hours_default
        )
        if inactive_since > timedelta(hours=cap_hours):
            await repo.delete_user_session(session, cmd.refresh_session_id)
            auth_events.emit(
                auth_events.SESSION_INACTIVE_EXPIRED,
                user_id=cmd.user_id,
                session_id=cmd.refresh_session_id,
                inactive_hours=int(inactive_since.total_seconds() / 3600),
            )
            raise ServiceError("Сессия истекла по неактивности", 401)

    expires_at = user_session["expires_at"]
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at <= datetime.now(UTC):
        await repo.delete_user_session(session, cmd.refresh_session_id)
        raise ServiceError("Refresh token истёк", 401)

    if user_session["refresh_token_hash"] != hash_refresh_token(cmd.refresh_token):
        # Hash mismatch after a valid session-id lookup = reuse of an already
        # rotated refresh token. Either the legitimate client is racing itself
        # or the token was stolen. Can't tell the two apart — kill every
        # session this user has, force re-auth from all devices.
        deleted = await repo.delete_all_user_sessions(session, cmd.user_id)
        auth_events.emit(
            auth_events.REFRESH_REUSE_DETECTED,
            user_id=cmd.user_id,
            sessions_killed=deleted,
        )
        raise ServiceError("Недействительный refresh token", 401)

    # TODO #47-tail: validate jti from payload against user_session.refresh_jti once column exists

    tokens = await build_tokens(user, session, refresh_session_id=cmd.refresh_session_id)
    auth_events.emit(
        auth_events.REFRESH_ROTATED,
        user_id=cmd.user_id,
        session_id=cmd.refresh_session_id,
    )
    return tokens


async def handle_logout(refresh_session_id: UUID, session: AsyncSession) -> None:
    await repo.delete_user_session(session, refresh_session_id)
    auth_events.emit(auth_events.LOGOUT, session_id=refresh_session_id)


async def handle_revoke_all_sessions(
    user_id: UUID,
    session: AsyncSession,
    *,
    except_session_id: UUID | None = None,
) -> int:
    """Kill every refresh session for ``user_id`` (user-initiated 'sign out everywhere').

    ``except_session_id`` — optional: keep that specific session alive. Used by
    self-service "logout on other devices" semantics (``?except_current=true``).
    """
    count = await repo.delete_all_user_sessions(
        session, user_id, except_session_id=except_session_id
    )
    auth_events.emit(
        auth_events.SESSIONS_REVOKED_ALL,
        user_id=user_id,
        sessions_killed=count,
    )
    return int(count)


async def _resolve_companies(
    companies_payload: list[dict[str, Any]],
    session: AsyncSession,
) -> tuple[list[dict[str, Any]], list[UUID]]:
    company_rows: list[dict[str, Any]] = []
    company_ids: list[UUID] = []
    for company_payload in companies_payload:
        company = await company_repo.create_or_get_company(
            session, cast("CompanyPayload", company_payload)
        )
        if company and company["id"] not in company_ids:
            company_rows.append(company)
            company_ids.append(company["id"])
    return company_rows, company_ids


async def _link_existing_user_companies(
    session: AsyncSession,
    user_id: UUID,
    company_rows: list[dict[str, Any]],
    current_company_id: UUID | None,
) -> UUID | None:
    if not company_rows:
        return current_company_id

    existing_user_companies = await company_repo.list_user_companies(session, user_id)
    existing_company_ids = {c["id"] for c in existing_user_companies}

    new_links = [
        (
            c["id"],
            "administrator" if c.get("is_new") else "employee",
            bool(c.get("is_new")),
            bool(c.get("is_new")),
        )
        for c in company_rows
        if c["id"] not in existing_company_ids
    ]
    if new_links:
        await company_repo.insert_user_company_links(session, user_id, new_links)

    primary_cid = current_company_id
    if not current_company_id:
        await company_repo.set_primary_company_if_absent(
            session, user_id, company_rows[0]["id"]
        )
        primary_cid = company_rows[0]["id"]

    await company_repo.upsert_company_select_history(
        session, user_id, company_rows[0]["id"]
    )
    return primary_cid


async def _handle_register_existing_user(
    cmd: RegisterCommand,
    session: AsyncSession,
) -> RegisterResult | MfaStepUpRequired | MfaSetupRequired:
    if not cmd.code:
        raise UserAlreadyExistsError()

    if await phone_lockout.is_locked(cmd.phone):
        auth_events.emit(
            auth_events.PHONE_LOCKED,
            phone=cmd.phone,
            reason="too_many_failed_otp",
        )
        raise ServiceError(
            "Слишком много неудачных попыток. Попробуйте позже.", 429
        )

    if not await repo.verify_code(session, cmd.phone, cmd.code):
        failures = await phone_lockout.register_failure(cmd.phone)
        auth_events.emit(
            auth_events.LOGIN_FAILED,
            phone=cmd.phone,
            reason="invalid_code",
            failures=failures,
        )
        raise InvalidVerificationCodeError()

    await phone_lockout.clear(cmd.phone)

    user = await repo.find_user_by_phone(session, cmd.phone)
    if not user:
        raise UserNotFoundError()
    if not user["is_active"]:
        raise UserDeactivatedError()

    if not user.get("phone_verified"):
        old_verified = user.get("phone_verified")
        user = await repo.set_phone_verified(session, cmd.phone)
        from infrastructure.messaging.status_events import (
            emit_client_status_changed,
        )

        emit_client_status_changed(
            user_id=user["id"],
            field="phone_verified",
            old_value=old_verified,
            new_value=True,
            changed_by=user["id"],
        )

    company_rows, _ = await _resolve_companies(cmd.companies, session)
    user["company_id"] = await _link_existing_user_companies(
        session, user["id"], company_rows, user.get("company_id")
    )

    await _enrich_companies(
        session, [c["inn"] for c in company_rows if c.get("inn")]
    )
    await repo.delete_codes(session, cmd.phone)

    from application.commands.mfa import (
        build_mfa_setup_required,
        build_mfa_step_up,
    )

    if user.get("mfa_enabled"):
        auth_events.emit(
            auth_events.LOGIN_REQUESTED,
            user_id=user["id"],
            phone=user["phone"],
            role=user["role"],
            stage="mfa_pending",
        )
        return build_mfa_step_up(user["id"])

    if is_mfa_required(user["role"]):
        auth_events.emit(
            auth_events.MFA_SETUP_REQUIRED,
            user_id=user["id"],
            phone=user["phone"],
            role=user["role"],
        )
        return build_mfa_setup_required(user["id"])

    active_cid, active_role = await employees_repository.get_active_company_and_role(
        session, user["id"], user["role"] or "client"
    )
    user_for_tokens = dict(user)
    if active_role and active_role != "client":
        user_for_tokens["role"] = active_role
    if active_cid and not user_for_tokens.get("company_id"):
        user_for_tokens["company_id"] = active_cid

    effective_role = user_for_tokens.get("role") or user["role"]
    auth_events.emit(
        auth_events.LOGIN_SUCCEEDED,
        user_id=user["id"],
        phone=user["phone"],
        role=effective_role,
        via="registration",
    )
    ctx = cmd.request_context or RequestContext()
    tokens = await build_tokens(
        cast("UserDict", user_for_tokens),
        session,
        ip_address=ctx.ip_address,
        user_agent=ctx.user_agent,
        country_code=ctx.country_code,
    )
    target_company_id = company_rows[0]["id"] if company_rows else active_cid
    formatted_user = await _format_user_with_permissions(
        session,
        cast("UserDict", user_for_tokens),
        target_company_id,
    )
    return RegisterResult(
        verified=True,
        phone=cmd.phone,
        message="Компании успешно добавлены",
        user=formatted_user,
        tokens=tokens,
    )


async def _handle_register_new_user(
    cmd: RegisterCommand,
    session: AsyncSession,
) -> RegisterResult:
    verified_from_code = False
    if cmd.code:
        if await phone_lockout.is_locked(cmd.phone):
            auth_events.emit(
                auth_events.PHONE_LOCKED,
                phone=cmd.phone,
                reason="too_many_failed_otp",
            )
            raise ServiceError(
                "Слишком много неудачных попыток. Попробуйте позже.", 429
            )
        if not await repo.verify_code(session, cmd.phone, cmd.code):
            failures = await phone_lockout.register_failure(cmd.phone)
            auth_events.emit(
                auth_events.LOGIN_FAILED,
                phone=cmd.phone,
                reason="invalid_code",
                failures=failures,
            )
            raise InvalidVerificationCodeError()
        await phone_lockout.clear(cmd.phone)
        verified_from_code = True

    company_rows, _ = await _resolve_companies(cmd.companies, session)

    primary_company = company_rows[0] if company_rows else None
    user = await repo.create_user(
        session,
        phone=cmd.phone,
        email=cmd.email,
        name=cmd.name,
        password_hash=_make_placeholder_password_hash(),
        company_id=primary_company["id"] if primary_company else None,
        phone_verified=verified_from_code,
    )

    if company_rows:
        links = [
            (
                c["id"],
                "administrator" if c.get("is_new") else "employee",
                bool(c.get("is_new")),
                bool(c.get("is_new")),
            )
            for c in company_rows
        ]
        await company_repo.insert_user_company_links(session, user["id"], links)
        await company_repo.upsert_company_select_history(
            session, user["id"], company_rows[0]["id"]
        )

    if verified_from_code:
        await repo.delete_codes(session, cmd.phone)
        await _enrich_companies(session, [c["inn"] for c in company_rows if c.get("inn")])
        ctx = cmd.request_context or RequestContext()
        tokens = await build_tokens(
            user,
            session,
            ip_address=ctx.ip_address,
            user_agent=ctx.user_agent,
            country_code=ctx.country_code,
        )
        auth_events.emit(
            auth_events.LOGIN_SUCCEEDED,
            user_id=user["id"],
            phone=user["phone"],
            role=user["role"],
            via="registration",
        )
        return RegisterResult(
            verified=True,
            phone=cmd.phone,
            message="Регистрация завершена",
            user=await _format_user_with_permissions(
                session,
                user,
                company_rows[0]["id"] if company_rows else None,
            ),
            tokens=tokens,
        )

    verification_code = get_verification_code(cmd.phone)
    await repo.save_verification_code(
        session, cmd.phone, verification_code, _make_expires_at()
    )
    _fire_sms(cmd.phone, verification_code, "registration")

    await _enrich_companies(session, [c["inn"] for c in company_rows if c.get("inn")])

    return RegisterResult(
        verified=False,
        phone=cmd.phone,
        message="Код подтверждения отправлен на ваш телефон",
    )


async def handle_register(
    cmd: RegisterCommand,
    session: AsyncSession,
) -> RegisterResult | MfaStepUpRequired | MfaSetupRequired:
    if await repo.phone_exists(session, cmd.phone):
        return await _handle_register_existing_user(cmd, session)
    return await _handle_register_new_user(cmd, session)


async def _enrich_companies(session: AsyncSession, inns: list[str]) -> None:
    """Synchronously enrich companies from DaData; failures are logged, not raised."""
    if not inns:
        return
    provider = get_company_lookup_provider()
    for inn in inns:
        try:
            data = await provider.enrich_by_inn(inn)
            if data:
                await company_repo.save_dadata_enrichment(session, inn, data)
            else:
                await company_repo.create_or_update_pending_enrichment(session, inn)
        except CompanyLookupUnavailableError:
            logger.warning("DaData enrichment unavailable for INN %s", inn)
            await company_repo.create_or_update_pending_enrichment(session, inn)
        except Exception:
            logger.exception("DaData enrichment failed for INN %s", inn)
            await company_repo.create_or_update_pending_enrichment(session, inn)


async def handle_magic_consume(
    cmd: MagicLinkConsumeCommand, session: AsyncSession
) -> AuthResult:
    """Consume a one-shot magic link: activate the user + issue tokens.

    Used by invited CEO / founders who receive an SMS with a short URL —
    clicking it lands them on `/s/{token}`, the frontend POSTs the token
    here, and we mark the user as active + phone-verified and return an
    auth session (same shape as a verified login).

    Failure modes return ``ServiceError`` mapped to 410 Gone by the router —
    an invalid link is not a retriable error.
    """
    link = await magic_link_repo.get_valid_by_token(session, cmd.token)
    if link is None:
        raise ServiceError("Ссылка недействительна или уже была использована", 410)
    user = await repo.find_user_by_id(session, link["user_id"])
    if user is None:
        raise ServiceError("Пользователь не найден", 410)

    await repo.activate_invited_user(session, user_id=user["id"])
    # Re-fetch so token includes latest role/company_id (activation may
    # touch neither today, but the pattern survives future changes).
    user = await repo.find_user_by_id(session, link["user_id"])
    if user is None:
        raise ServiceError("Пользователь не найден после активации", 500)

    tokens = await build_tokens(
        user,
        session,
        ip_address=cmd.ctx.ip_address,
        user_agent=cmd.ctx.user_agent,
        country_code=cmd.ctx.country_code,
    )
    await magic_link_repo.consume(session, link["id"])
    auth_events.emit(auth_events.LOGIN_SUCCEEDED, user_id=user["id"])
    return AuthResult(user=_format_user(user), tokens=tokens)
