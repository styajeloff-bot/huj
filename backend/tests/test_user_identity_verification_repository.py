from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.models.users import User
from infrastructure.repositories import user_identity_verification_repository as repo

pytestmark = pytest.mark.asyncio


async def test_identity_verification_repository_lifecycle(
    db_session: AsyncSession,
) -> None:
    user = User(
        phone="+76662150201",
        email="mobile-id-repo@test.local",
        name="Mobile ID Repo",
        role="client",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()

    expires_at = datetime.now(UTC) + timedelta(minutes=10)
    created = await repo.create_attempt(
        db_session,
        user_id=user.id,
        provider=repo.PROVIDER_MOBILE_ID,
        phone_number=user.phone,
        expires_at=expires_at,
    )

    assert created["id"]
    assert created["user_id"] == user.id
    assert created["provider"] == repo.PROVIDER_MOBILE_ID
    assert created["status"] == repo.STATUS_PENDING
    assert created["correlation_id"]
    assert created["expires_at"] == expires_at

    by_correlation = await repo.get_by_correlation_id(
        db_session, created["correlation_id"]
    )
    assert by_correlation is not None
    assert by_correlation["id"] == created["id"]

    sms_requested = await repo.mark_sms_requested(
        db_session,
        verification_id=created["id"],
        auth_req_id="auth-21502",
    )
    assert sms_requested is not None
    assert sms_requested["status"] == repo.STATUS_SMS_REQUESTED
    assert sms_requested["auth_req_id"] == "auth-21502"
    assert sms_requested["sms_requested_at"] is not None

    verified = await repo.mark_verified(
        db_session,
        verification_id=created["id"],
        mobile_id_sub="sub-21502",
        phone_number=user.phone,
        birthdate_match="Y",
        given_name="Ivan",
        middle_name="Ivanovich",
        family_name="Ivanov",
        national_identifier_masked="1234******",
    )
    assert verified is not None
    assert verified["status"] == repo.STATUS_VERIFIED
    assert verified["mobile_id_sub"] == "sub-21502"
    assert verified["verified_at"] is not None

    latest = await repo.get_latest_verified_for_user(
        db_session, user_id=user.id, provider=repo.PROVIDER_MOBILE_ID
    )
    assert latest is not None
    assert latest["id"] == created["id"]


async def test_identity_verification_repository_marks_failed(
    db_session: AsyncSession,
) -> None:
    user = User(
        phone="+76662150202",
        email="mobile-id-failed@test.local",
        name="Mobile ID Failed",
        role="client",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()

    created = await repo.create_attempt(
        db_session,
        user_id=user.id,
        provider=repo.PROVIDER_MOBILE_ID,
        phone_number=user.phone,
        correlation_id=uuid4(),
        expires_at=datetime.now(UTC) + timedelta(minutes=10),
    )

    failed = await repo.mark_failed(
        db_session,
        verification_id=created["id"],
        failure_code="kyc_mismatch",
        failure_message="Дата рождения не совпала",
    )
    assert failed is not None
    assert failed["status"] == repo.STATUS_FAILED
    assert failed["failure_code"] == "kyc_mismatch"
    assert failed["failure_message"] == "Дата рождения не совпала"
    assert failed["failed_at"] is not None

    latest = await repo.get_latest_verified_for_user(
        db_session, user_id=user.id, provider=repo.PROVIDER_MOBILE_ID
    )
    assert latest is None
