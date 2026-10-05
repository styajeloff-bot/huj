from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any, cast
from uuid import UUID

from redis.exceptions import RedisError
from sqlalchemy.ext.asyncio import AsyncSession

from application.errors import ServiceError
from application.services.passport_profile_fields import (
    PASSPORT_MAIN_TYPE,
    profile_autofill_from_passport_records,
)
from domain.services.identity_verification import IdentityVerificationProvider
from infrastructure.cache import get_redis
from infrastructure.repositories import (
    client_repository,
    passport_recognition_repository,
)
from infrastructure.repositories import user_identity_verification_repository as repo
from infrastructure.services.mobile_id.client import (
    MobileIdProviderPendingError,
    MobileIdProviderUnavailableError,
    get_mobile_id_provider,
)
from infrastructure.settings import settings


@dataclass(frozen=True)
class StartIdentityVerificationCommand:
    user_id: UUID
    birth_date: date | None = None
    provider: IdentityVerificationProvider | None = None


@dataclass(frozen=True)
class SubmitIdentityVerificationSmsCodeCommand:
    user_id: UUID
    verification_id: UUID
    code: str
    provider: IdentityVerificationProvider | None = None


@dataclass(frozen=True)
class HandleMobileIdSmsOtpNotificationCommand:
    correlation_id: UUID
    auth_req_id: str
    smsotp_endpoint: str
    leading_kyc_match: bool | None = None


@dataclass(frozen=True)
class HandleMobileIdNotificationCommand:
    correlation_id: UUID
    id_token: str
    access_token: str
    jwks_uri: str | None = None
    leading_kyc_match: bool | None = None
    provider: IdentityVerificationProvider | None = None


def _provider(
    override: IdentityVerificationProvider | None,
) -> IdentityVerificationProvider:
    return override or get_mobile_id_provider()


def _attempt_payload(row: dict[str, Any], *, phone_masked: str | None = None) -> dict[str, Any]:
    return {
        "verification_id": row["id"],
        "correlation_id": row["correlation_id"],
        "status": row["status"],
        "verified": row["status"] == repo.STATUS_VERIFIED,
        "verified_at": row.get("verified_at"),
        "provider": row.get("provider"),
        "phone_masked": phone_masked or _mask_phone(row.get("phone_number")),
        "expires_at": row.get("expires_at"),
        "failure_message": row.get("failure_message"),
    }


def _mask_phone(phone: str | None) -> str | None:
    if not phone:
        return None
    digits = "".join(ch for ch in phone if ch.isdigit())
    suffix = digits[-3:] if len(digits) >= 3 else digits
    return f"+7 *** *** *{suffix}" if suffix else None


def _profile_name_fields(profile: dict[str, Any] | None) -> tuple[str | None, str | None, str | None]:
    if profile is None:
        return None, None, None
    parts = str(profile.get("name") or "").split()
    if len(parts) < 2:
        return None, None, None
    family_name = parts[0]
    given_name = parts[1]
    middle_name = " ".join(parts[2:]) if len(parts) > 2 else None
    return family_name, given_name, middle_name


async def _store_sms_endpoint(
    verification_id: UUID, correlation_id: UUID, smsotp_endpoint: str
) -> None:
    value = json.dumps({"smsotp_endpoint": smsotp_endpoint})
    ttl = settings.mobile_id_attempt_ttl_seconds
    try:
        redis = get_redis()
        await redis.set(f"mobile-id:verification:{verification_id}:sms", value, ex=ttl)
        await redis.set(f"mobile-id:correlation:{correlation_id}:sms", value, ex=ttl)
    except (RedisError, RuntimeError):
        return


async def _load_sms_endpoint(
    verification_id: UUID,
    correlation_id: UUID,
) -> str | None:
    try:
        redis = get_redis()
        raw = await redis.get(f"mobile-id:verification:{verification_id}:sms")
        if raw is None:
            raw = await redis.get(f"mobile-id:correlation:{correlation_id}:sms")
    except (RedisError, RuntimeError):
        return None
    if raw is None:
        return None
    raw_text = raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError:
        return None
    endpoint = data.get("smsotp_endpoint")
    return str(endpoint) if endpoint else None


async def _resolve_birthdate(
    session: AsyncSession,
    *,
    user_id: UUID,
    requested_birthdate: date | None,
    profile_birthdate: Any,
) -> date | None:
    if requested_birthdate is not None:
        return requested_birthdate
    if isinstance(profile_birthdate, date):
        return profile_birthdate
    main = await passport_recognition_repository.get_latest_for_user(
        session,
        user_id=user_id,
        passport_type=PASSPORT_MAIN_TYPE,
    )
    payload = profile_autofill_from_passport_records(
        main=main,
        registration=None,
    )
    birthdate = payload.get("birth_date")
    return birthdate if isinstance(birthdate, date) else None


async def handle_start_identity_verification(
    cmd: StartIdentityVerificationCommand,
    session: AsyncSession,
) -> dict[str, Any]:
    profile = await client_repository.get_profile_with_user(session, cmd.user_id)
    if profile is None:
        raise ServiceError("Пользователь не найден", 404)
    birthdate = await _resolve_birthdate(
        session,
        user_id=cmd.user_id,
        requested_birthdate=cmd.birth_date,
        profile_birthdate=profile.get("birth_date"),
    )
    if birthdate is None:
        raise ServiceError("Для верификации укажите дату рождения", 422)
    family_name, given_name, middle_name = _profile_name_fields(profile)
    if not family_name or not given_name:
        raise ServiceError("Для верификации укажите ФИО", 422)
    phone = str(profile.get("phone") or "")
    if not phone:
        raise ServiceError("Для верификации нужен телефон пользователя", 422)

    expires_at = datetime.now(UTC) + timedelta(seconds=settings.mobile_id_attempt_ttl_seconds)
    attempt = await repo.create_attempt(
        session,
        user_id=cmd.user_id,
        provider=repo.PROVIDER_MOBILE_ID,
        phone_number=phone,
        birthdate=birthdate,
        expires_at=expires_at,
    )
    try:
        started = await _provider(cmd.provider).start(
            user_id=cmd.user_id,
            phone_number=phone,
            birthdate=birthdate,
            correlation_id=attempt["correlation_id"],
            family_name=family_name,
            given_name=given_name,
            middle_name=middle_name,
        )
    except MobileIdProviderUnavailableError as exc:
        message = str(exc)
        await repo.mark_failed(
            session,
            verification_id=attempt["id"],
            failure_code="provider_unavailable",
            failure_message=message,
        )
        raise ServiceError(message, exc.status_code) from exc

    row = await repo.mark_sms_requested(
        session,
        verification_id=attempt["id"],
        auth_req_id=started.auth_req_id,
    )
    if row is None:
        raise ServiceError("Попытка верификации не найдена", 404)
    return _attempt_payload(row, phone_masked=started.phone_masked)


async def handle_submit_identity_verification_sms_code(
    cmd: SubmitIdentityVerificationSmsCodeCommand,
    session: AsyncSession,
) -> dict[str, Any]:
    attempt = await repo.get_by_id(session, cmd.verification_id)
    if attempt is None:
        raise ServiceError("Попытка верификации не найдена", 404)
    if attempt["user_id"] != cmd.user_id:
        raise ServiceError("Нет доступа к попытке верификации", 403)
    if attempt["status"] == repo.STATUS_VERIFIED:
        return _attempt_payload(attempt)
    try:
        data = await _provider(cmd.provider).submit_sms_code(
            auth_req_id=attempt.get("auth_req_id"),
            smsotp_endpoint=await _load_sms_endpoint(
                cmd.verification_id,
                attempt["correlation_id"],
            ),
            code=cmd.code,
            phone_number=attempt.get("phone_number"),
            birthdate=attempt.get("birthdate"),
        )
    except MobileIdProviderPendingError:
        return _attempt_payload(attempt)
    except MobileIdProviderUnavailableError as exc:
        message = str(exc)
        failed = await repo.mark_failed(
            session,
            verification_id=cmd.verification_id,
            failure_code="provider_error",
            failure_message=message,
        )
        if failed is None:
            raise ServiceError("Попытка верификации не найдена", 404) from exc
        raise ServiceError(message, exc.status_code) from exc

    if not data.matched:
        failed = await repo.mark_failed(
            session,
            verification_id=cmd.verification_id,
            failure_code="profile_identity_mismatch",
            failure_message=(
                "Данные профиля не совпадают с данными Mobile ID. "
                "Проверьте ФИО и дату рождения."
            ),
        )
        if failed is None:
            raise ServiceError("Попытка верификации не найдена", 404)
        return _attempt_payload(failed)

    verified = await repo.mark_verified(
        session,
        verification_id=cmd.verification_id,
        mobile_id_sub=data.mobile_id_sub,
        phone_number=data.phone_number,
        birthdate=data.birthdate,
        birthdate_match=data.birthdate_match,
        given_name=data.given_name,
        middle_name=data.middle_name,
        family_name=data.family_name,
        national_identifier_masked=data.national_identifier_masked,
    )
    if verified is None:
        raise ServiceError("Попытка верификации не найдена", 404)
    return _attempt_payload(verified)


async def handle_mobile_id_sms_otp_notification(
    cmd: HandleMobileIdSmsOtpNotificationCommand,
    session: AsyncSession,
) -> dict[str, Any]:
    attempt = await repo.get_by_correlation_id(session, cmd.correlation_id)
    if attempt is None:
        raise ServiceError("Попытка верификации не найдена", 404)
    await _store_sms_endpoint(attempt["id"], cmd.correlation_id, cmd.smsotp_endpoint)
    row = await repo.mark_sms_requested(
        session,
        verification_id=attempt["id"],
        auth_req_id=cmd.auth_req_id,
    )
    if row is None:
        raise ServiceError("Попытка верификации не найдена", 404)
    return cast("dict[str, Any]", row)


async def handle_mobile_id_notification(
    cmd: HandleMobileIdNotificationCommand,
    session: AsyncSession,
) -> dict[str, Any]:
    attempt = await repo.get_by_correlation_id(session, cmd.correlation_id)
    if attempt is None:
        raise ServiceError("Попытка верификации не найдена", 404)
    if attempt["status"] == repo.STATUS_VERIFIED:
        return cast("dict[str, Any]", attempt)
    profile = await client_repository.get_profile_with_user(session, attempt["user_id"])
    family_name, given_name, middle_name = _profile_name_fields(profile)
    try:
        data = await _provider(cmd.provider).handle_notification(
            id_token=cmd.id_token,
            access_token=cmd.access_token,
            jwks_uri=cmd.jwks_uri,
            phone_number=attempt.get("phone_number"),
            birthdate=attempt.get("birthdate"),
            family_name=family_name,
            given_name=given_name,
            middle_name=middle_name,
        )
    except MobileIdProviderUnavailableError as exc:
        message = str(exc)
        failed = await repo.mark_failed(
            session,
            verification_id=attempt["id"],
            failure_code="provider_error",
            failure_message=message,
        )
        if failed is None:
            raise ServiceError("Попытка верификации не найдена", 404) from exc
        return cast("dict[str, Any]", failed)
    verified = await repo.mark_verified(
        session,
        verification_id=attempt["id"],
        mobile_id_sub=data.mobile_id_sub,
        phone_number=data.phone_number,
        birthdate=data.birthdate,
        birthdate_match=data.birthdate_match,
        given_name=data.given_name,
        middle_name=data.middle_name,
        family_name=data.family_name,
        national_identifier_masked=data.national_identifier_masked,
    )
    if verified is None:
        raise ServiceError("Попытка верификации не найдена", 404)
    return cast("dict[str, Any]", verified)
