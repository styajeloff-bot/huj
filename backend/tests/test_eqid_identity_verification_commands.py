from __future__ import annotations

from datetime import date
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from application.commands.identity_verification import (
    StartIdentityVerificationCommand,
    SubmitIdentityVerificationSmsCodeCommand,
    handle_start_identity_verification,
    handle_submit_identity_verification_sms_code,
)
from domain.services.identity_verification import (
    IdentityVerificationData,
    IdentityVerificationStarted,
)
from infrastructure.models.users import ClientProfile, User
from infrastructure.services.mobile_id.client import LocalMobileIdProvider

pytestmark = pytest.mark.asyncio


class EqidContractProvider(LocalMobileIdProvider):
    def __init__(self, *, matched: bool) -> None:
        self.matched = matched
        self.start_fields: dict[str, Any] = {}

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
        self.start_fields = {
            "family_name": family_name,
            "given_name": given_name,
            "middle_name": middle_name,
        }
        return await super().start(
            user_id=user_id,
            phone_number=phone_number,
            birthdate=birthdate,
            correlation_id=correlation_id,
        )

    async def submit_sms_code(self, **kwargs: Any) -> IdentityVerificationData:
        data = await super().submit_sms_code(**kwargs)
        return IdentityVerificationData(
            mobile_id_sub=data.mobile_id_sub,
            matched=self.matched,
            phone_number=data.phone_number,
            birthdate=data.birthdate,
            birthdate_match=data.birthdate_match,
            given_name=data.given_name,
            middle_name=data.middle_name,
            family_name=data.family_name,
            national_identifier_masked=data.national_identifier_masked,
        )


async def _start_attempt(
    db_session: AsyncSession,
    provider: EqidContractProvider,
    *,
    email: str,
) -> tuple[dict[str, Any], UUID]:
    user = User(
        phone="+79186847414",
        email=email,
        name="Иванов Иван Иванович",
        role="client",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    db_session.add(ClientProfile(user_id=user.id, birth_date=date(1991, 1, 8)))
    await db_session.flush()

    started = await handle_start_identity_verification(
        StartIdentityVerificationCommand(user_id=user.id, provider=provider),
        db_session,
    )
    return started, user.id


async def test_start_passes_profile_names_to_eqid_provider(
    db_session: AsyncSession,
) -> None:
    provider = EqidContractProvider(matched=True)

    await _start_attempt(
        db_session,
        provider,
        email="eqid-start-contract@test.local",
    )

    assert provider.start_fields == {
        "family_name": "Иванов",
        "given_name": "Иван",
        "middle_name": "Иванович",
    }


async def test_unmatched_eqid_result_fails_attempt_without_verifying(
    db_session: AsyncSession,
) -> None:
    provider = EqidContractProvider(matched=False)
    started, user_id = await _start_attempt(
        db_session,
        provider,
        email="eqid-unmatched@test.local",
    )

    result = await handle_submit_identity_verification_sms_code(
        SubmitIdentityVerificationSmsCodeCommand(
            user_id=user_id,
            verification_id=started["verification_id"],
            code="0000",
            provider=provider,
        ),
        db_session,
    )

    assert result["status"] == "failed"
    assert result["verified"] is False
    assert result["failure_message"] == (
        "Данные профиля не совпадают с данными Mobile ID. "
        "Проверьте ФИО и дату рождения."
    )
