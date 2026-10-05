from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any, cast
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from domain.values import IdentityVerificationStatus
from infrastructure.models.users import UserIdentityVerification
from infrastructure.repository_timing import timed_repository

PROVIDER_MOBILE_ID = "mobile_id"

STATUS_PENDING = IdentityVerificationStatus.PENDING.value
STATUS_SMS_REQUESTED = IdentityVerificationStatus.SMS_REQUESTED.value
STATUS_SMS_VERIFIED = IdentityVerificationStatus.SMS_VERIFIED.value
STATUS_VERIFIED = IdentityVerificationStatus.VERIFIED.value
STATUS_DATA_RECEIVED = IdentityVerificationStatus.DATA_RECEIVED.value
STATUS_FAILED = IdentityVerificationStatus.FAILED.value
STATUS_EXPIRED = IdentityVerificationStatus.EXPIRED.value


def _to_dict(record: UserIdentityVerification) -> dict[str, Any]:
    return {
        "id": record.id,
        "user_id": record.user_id,
        "provider": record.provider,
        "status": record.status,
        "auth_req_id": record.auth_req_id,
        "correlation_id": record.correlation_id,
        "mobile_id_sub": record.mobile_id_sub,
        "phone_number": record.phone_number,
        "birthdate": record.birthdate,
        "birthdate_match": record.birthdate_match,
        "given_name": record.given_name,
        "middle_name": record.middle_name,
        "family_name": record.family_name,
        "national_identifier_masked": record.national_identifier_masked,
        "failure_code": record.failure_code,
        "failure_message": record.failure_message,
        "started_at": record.started_at,
        "sms_requested_at": record.sms_requested_at,
        "verified_at": record.verified_at,
        "failed_at": record.failed_at,
        "expires_at": record.expires_at,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
    }


@timed_repository
async def create_attempt(
    session: AsyncSession,
    *,
    user_id: UUID,
    provider: str = PROVIDER_MOBILE_ID,
    phone_number: str | None,
    expires_at: datetime,
    correlation_id: UUID | None = None,
    birthdate: date | None = None,
) -> dict[str, Any]:
    now = datetime.now(UTC)
    record = UserIdentityVerification(
        user_id=user_id,
        provider=provider,
        status=STATUS_PENDING,
        correlation_id=correlation_id or uuid4(),
        phone_number=phone_number,
        birthdate=birthdate,
        started_at=now,
        expires_at=expires_at,
        created_at=now,
        updated_at=now,
    )
    session.add(record)
    await session.flush()
    await session.refresh(record)
    return _to_dict(record)


@timed_repository
async def get_by_id(
    session: AsyncSession, verification_id: UUID
) -> dict[str, Any] | None:
    record = await session.get(UserIdentityVerification, verification_id)
    return _to_dict(record) if record else None


@timed_repository
async def get_by_correlation_id(
    session: AsyncSession, correlation_id: UUID
) -> dict[str, Any] | None:
    result = await session.execute(
        sa.select(UserIdentityVerification).where(
            UserIdentityVerification.correlation_id == correlation_id
        )
    )
    record = result.scalars().first()
    return _to_dict(record) if record else None


@timed_repository
async def get_latest_for_user(
    session: AsyncSession, *, user_id: UUID, provider: str = PROVIDER_MOBILE_ID
) -> dict[str, Any] | None:
    result = await session.execute(
        sa.select(UserIdentityVerification)
        .where(
            UserIdentityVerification.user_id == user_id,
            UserIdentityVerification.provider == provider,
        )
        .order_by(UserIdentityVerification.created_at.desc())
        .limit(1)
    )
    record = result.scalars().first()
    return _to_dict(record) if record else None


@timed_repository
async def get_latest_verified_for_user(
    session: AsyncSession, *, user_id: UUID, provider: str = PROVIDER_MOBILE_ID
) -> dict[str, Any] | None:
    result = await session.execute(
        sa.select(UserIdentityVerification)
        .where(
            UserIdentityVerification.user_id == user_id,
            UserIdentityVerification.provider == provider,
            UserIdentityVerification.status == STATUS_VERIFIED,
        )
        .order_by(UserIdentityVerification.verified_at.desc().nullslast())
        .limit(1)
    )
    record = result.scalars().first()
    return _to_dict(record) if record else None


@timed_repository
async def expire_verified_for_user(
    session: AsyncSession,
    *,
    user_id: UUID,
    provider: str = PROVIDER_MOBILE_ID,
    failure_code: str = "profile_identity_changed",
    failure_message: str = "Данные профиля изменены. Пройдите верификацию заново.",
) -> int:
    now = datetime.now(UTC)
    result = await session.execute(
        sa.update(UserIdentityVerification)
        .where(
            UserIdentityVerification.user_id == user_id,
            UserIdentityVerification.provider == provider,
            UserIdentityVerification.status == STATUS_VERIFIED,
        )
        .values(
            status=STATUS_EXPIRED,
            failure_code=failure_code,
            failure_message=failure_message,
            verified_at=None,
            updated_at=now,
        )
    )
    await session.flush()
    return int(cast("Any", result).rowcount or 0)


async def _current(
    session: AsyncSession, verification_id: UUID
) -> UserIdentityVerification | None:
    return await session.get(UserIdentityVerification, verification_id)


@timed_repository
async def mark_sms_requested(
    session: AsyncSession,
    *,
    verification_id: UUID,
    auth_req_id: str,
) -> dict[str, Any] | None:
    record = await _current(session, verification_id)
    if record is None:
        return None
    if record.status in {STATUS_VERIFIED, STATUS_DATA_RECEIVED}:
        return _to_dict(record)
    now = datetime.now(UTC)
    result = await session.execute(
        sa.update(UserIdentityVerification)
        .where(UserIdentityVerification.id == verification_id)
        .values(
            status=STATUS_SMS_REQUESTED,
            auth_req_id=auth_req_id,
            sms_requested_at=record.sms_requested_at or now,
            updated_at=now,
        )
        .returning(UserIdentityVerification)
    )
    updated = result.scalars().first()
    await session.flush()
    return _to_dict(updated) if updated else None


@timed_repository
async def mark_verified(
    session: AsyncSession,
    *,
    verification_id: UUID,
    mobile_id_sub: str,
    phone_number: str | None = None,
    birthdate: date | None = None,
    birthdate_match: str | None = None,
    given_name: str | None = None,
    middle_name: str | None = None,
    family_name: str | None = None,
    national_identifier_masked: str | None = None,
) -> dict[str, Any] | None:
    record = await _current(session, verification_id)
    if record is None:
        return None
    if record.status == STATUS_VERIFIED:
        return _to_dict(record)
    now = datetime.now(UTC)
    result = await session.execute(
        sa.update(UserIdentityVerification)
        .where(UserIdentityVerification.id == verification_id)
        .values(
            status=STATUS_VERIFIED,
            mobile_id_sub=mobile_id_sub,
            phone_number=phone_number or record.phone_number,
            birthdate=birthdate or cast("date | None", record.birthdate),
            birthdate_match=birthdate_match,
            given_name=given_name,
            middle_name=middle_name,
            family_name=family_name,
            national_identifier_masked=national_identifier_masked,
            failure_code=None,
            failure_message=None,
            verified_at=now,
            updated_at=now,
        )
        .returning(UserIdentityVerification)
    )
    updated = result.scalars().first()
    await session.flush()
    return _to_dict(updated) if updated else None


@timed_repository
async def mark_data_received(
    session: AsyncSession,
    *,
    verification_id: UUID,
    mobile_id_sub: str,
) -> dict[str, Any] | None:
    record = await _current(session, verification_id)
    if record is None:
        return None
    if record.status == STATUS_DATA_RECEIVED:
        return _to_dict(record)
    now = datetime.now(UTC)
    result = await session.execute(
        sa.update(UserIdentityVerification)
        .where(UserIdentityVerification.id == verification_id)
        .values(
            status=STATUS_DATA_RECEIVED,
            mobile_id_sub=mobile_id_sub,
            failure_code=None,
            failure_message=None,
            updated_at=now,
        )
        .returning(UserIdentityVerification)
    )
    updated = result.scalars().first()
    await session.flush()
    return _to_dict(updated) if updated else None


@timed_repository
async def mark_expired(
    session: AsyncSession,
    *,
    verification_id: UUID,
    failure_message: str,
) -> dict[str, Any] | None:
    record = await _current(session, verification_id)
    if record is None:
        return None
    now = datetime.now(UTC)
    result = await session.execute(
        sa.update(UserIdentityVerification)
        .where(UserIdentityVerification.id == verification_id)
        .values(
            status=STATUS_EXPIRED,
            failure_code="attempt_expired",
            failure_message=failure_message,
            updated_at=now,
        )
        .returning(UserIdentityVerification)
    )
    updated = result.scalars().first()
    await session.flush()
    return _to_dict(updated) if updated else None


@timed_repository
async def mark_failed(
    session: AsyncSession,
    *,
    verification_id: UUID,
    failure_code: str,
    failure_message: str,
) -> dict[str, Any] | None:
    record = await _current(session, verification_id)
    if record is None:
        return None
    if record.status in {STATUS_VERIFIED, STATUS_DATA_RECEIVED}:
        return _to_dict(record)
    now = datetime.now(UTC)
    result = await session.execute(
        sa.update(UserIdentityVerification)
        .where(UserIdentityVerification.id == verification_id)
        .values(
            status=STATUS_FAILED,
            failure_code=failure_code,
            failure_message=failure_message,
            failed_at=now,
            updated_at=now,
        )
        .returning(UserIdentityVerification)
    )
    updated = result.scalars().first()
    await session.flush()
    return _to_dict(updated) if updated else None
