from __future__ import annotations

from datetime import date

import pytest
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
from application.errors import ServiceError
from application.queries.identity_verification import (
    GetMyIdentityVerificationQuery,
    handle_get_my_identity_verification,
)
from domain.services.identity_verification import IdentityVerificationData
from infrastructure.models.users import ClientProfile, User
from infrastructure.repositories import passport_recognition_repository
from infrastructure.services.mobile_id.client import (
    LocalMobileIdProvider,
    MobileIdProviderPendingError,
    MobileIdProviderUnavailableError,
)

pytestmark = pytest.mark.asyncio


class RecordingMobileIdProvider(LocalMobileIdProvider):
    def __init__(self) -> None:
        self.notification_profile_fields: dict[str, object] = {}
        self.kyc_notification_calls = 0

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
        self.kyc_notification_calls += 1
        self.notification_profile_fields = {
            "phone_number": phone_number,
            "birthdate": birthdate,
            "family_name": family_name,
            "given_name": given_name,
            "middle_name": middle_name,
        }
        return IdentityVerificationData(
            mobile_id_sub=id_token,
            phone_number=phone_number,
            birthdate=birthdate,
            birthdate_match="Y",
            family_name=family_name,
            given_name=given_name,
            middle_name=middle_name,
        )

class PendingAfterSmsProvider(LocalMobileIdProvider):
    async def submit_sms_code(
        self,
        *,
        auth_req_id: str | None,
        smsotp_endpoint: str | None,
        code: str,
        phone_number: str | None,
        birthdate: date | None,
    ) -> IdentityVerificationData:
        _ = (auth_req_id, smsotp_endpoint, code, phone_number, birthdate)
        raise MobileIdProviderPendingError(
            "Код принят. Ожидаем подтверждение Mobile ID."
        )


class WrongSmsCodeProvider(LocalMobileIdProvider):
    async def submit_sms_code(
        self,
        *,
        auth_req_id: str | None,
        smsotp_endpoint: str | None,
        code: str,
        phone_number: str | None,
        birthdate: date | None,
    ) -> IdentityVerificationData:
        _ = (auth_req_id, smsotp_endpoint, code, phone_number, birthdate)
        raise MobileIdProviderUnavailableError(
            "Неверный код подтверждения. Проверьте SMS и попробуйте ещё раз.",
            status_code=422,
        )


async def test_start_and_submit_sms_with_local_provider_verifies_user(
    db_session: AsyncSession,
) -> None:
    provider = LocalMobileIdProvider()
    user = User(
        phone="+76662150211",
        email="mobile-id-command@test.local",
        name="Mobile ID Command",
        role="client",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    db_session.add(ClientProfile(user_id=user.id, birth_date=date(1991, 2, 3)))
    await db_session.flush()

    started = await handle_start_identity_verification(
        StartIdentityVerificationCommand(user_id=user.id, provider=provider),
        db_session,
    )
    assert started["status"] == "sms_requested"
    assert started["verification_id"]
    assert started["phone_masked"].endswith("211")

    submitted = await handle_submit_identity_verification_sms_code(
        SubmitIdentityVerificationSmsCodeCommand(
            user_id=user.id,
            verification_id=started["verification_id"],
            code="0000",
            provider=provider,
        ),
        db_session,
    )
    assert submitted["status"] == "verified"
    assert submitted["verified"] is True

    status = await handle_get_my_identity_verification(
        GetMyIdentityVerificationQuery(user_id=user.id),
        db_session,
    )
    assert status["verified"] is True
    assert status["provider"] == "mobile_id"
    assert status["status"] == "verified"


async def test_submit_sms_pending_after_accepted_code_waits_for_final_notification(
    db_session: AsyncSession,
) -> None:
    provider = PendingAfterSmsProvider()
    user = User(
        phone="+76662150216",
        email="mobile-id-sms-accepted-pending@test.local",
        name="Иванов Иван",
        role="client",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    db_session.add(ClientProfile(user_id=user.id, birth_date=date(1991, 2, 3)))
    await db_session.flush()

    started = await handle_start_identity_verification(
        StartIdentityVerificationCommand(user_id=user.id, provider=provider),
        db_session,
    )
    await handle_mobile_id_sms_otp_notification(
        HandleMobileIdSmsOtpNotificationCommand(
            correlation_id=started["correlation_id"],
            auth_req_id="auth-sms-accepted",
            smsotp_endpoint="https://mts.example/sms",
        ),
        db_session,
    )

    submitted = await handle_submit_identity_verification_sms_code(
        SubmitIdentityVerificationSmsCodeCommand(
            user_id=user.id,
            verification_id=started["verification_id"],
            code="1234",
            provider=provider,
        ),
        db_session,
    )

    assert submitted["status"] == "sms_requested"
    assert submitted["verified"] is False
    status = await handle_get_my_identity_verification(
        GetMyIdentityVerificationQuery(user_id=user.id),
        db_session,
    )
    assert status["status"] == "sms_requested"
    assert status["verified"] is False


async def test_submit_sms_provider_error_is_returned_to_user(
    db_session: AsyncSession,
) -> None:
    provider = WrongSmsCodeProvider()
    user = User(
        phone="+76662150217",
        email="mobile-id-sms-wrong-code@test.local",
        name="Иванов Иван",
        role="client",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    db_session.add(ClientProfile(user_id=user.id, birth_date=date(1991, 2, 3)))
    await db_session.flush()

    started = await handle_start_identity_verification(
        StartIdentityVerificationCommand(user_id=user.id, provider=provider),
        db_session,
    )
    await handle_mobile_id_sms_otp_notification(
        HandleMobileIdSmsOtpNotificationCommand(
            correlation_id=started["correlation_id"],
            auth_req_id="auth-sms-wrong",
            smsotp_endpoint="https://mts.example/sms",
        ),
        db_session,
    )

    with pytest.raises(ServiceError, match="Неверный код подтверждения") as exc_info:
        await handle_submit_identity_verification_sms_code(
            SubmitIdentityVerificationSmsCodeCommand(
                user_id=user.id,
                verification_id=started["verification_id"],
                code="1111",
                provider=provider,
            ),
            db_session,
        )

    assert exc_info.value.status_code == 422
    status = await handle_get_my_identity_verification(
        GetMyIdentityVerificationQuery(user_id=user.id),
        db_session,
    )
    assert status["status"] == "failed"
    assert status["failure_message"] == (
        "Неверный код подтверждения. Проверьте SMS и попробуйте ещё раз."
    )


async def test_start_uses_passport_recognition_birth_date_when_profile_empty(
    db_session: AsyncSession,
) -> None:
    provider = LocalMobileIdProvider()
    user = User(
        phone="+76662150213",
        email="mobile-id-passport-birthdate@test.local",
        name="Mobile ID Passport Birthdate",
        role="client",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    await passport_recognition_repository.save(
        db_session,
        user_id=user.id,
        file_hash="passport-birthdate-21502",
        passport_type="ceo_passport_page23",
        raw_data={
            "items": [
                {
                    "fields": {
                        "birth_date": {"text": "1993-05-06"},
                    },
                },
            ],
        },
        mapped_data={},
        confidence_data={},
        recognition_task_id=None,
    )

    started = await handle_start_identity_verification(
        StartIdentityVerificationCommand(user_id=user.id, provider=provider),
        db_session,
    )

    assert started["status"] == "sms_requested"
    submitted = await handle_submit_identity_verification_sms_code(
        SubmitIdentityVerificationSmsCodeCommand(
            user_id=user.id,
            verification_id=started["verification_id"],
            code="0000",
            provider=provider,
        ),
        db_session,
    )
    assert submitted["status"] == "verified"


async def test_start_requires_profile_full_name(
    db_session: AsyncSession,
) -> None:
    provider = LocalMobileIdProvider()
    user = User(
        phone="+76662150215",
        email="mobile-id-missing-name@test.local",
        name="Иван",
        role="client",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    db_session.add(ClientProfile(user_id=user.id, birth_date=date(1990, 1, 1)))
    await db_session.flush()

    with pytest.raises(ServiceError, match="Для верификации укажите ФИО"):
        await handle_start_identity_verification(
            StartIdentityVerificationCommand(user_id=user.id, provider=provider),
            db_session,
        )


async def test_mobile_id_notification_passes_profile_name_fields_to_provider(
    db_session: AsyncSession,
) -> None:
    provider = RecordingMobileIdProvider()
    user = User(
        phone="+76662150214",
        email="mobile-id-profile-match@test.local",
        name="Иванов Иван Иванович",
        role="client",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    db_session.add(ClientProfile(user_id=user.id, birth_date=date(1990, 1, 1)))
    await db_session.flush()

    started = await handle_start_identity_verification(
        StartIdentityVerificationCommand(user_id=user.id, provider=provider),
        db_session,
    )

    result = await handle_mobile_id_notification(
        HandleMobileIdNotificationCommand(
            correlation_id=started["correlation_id"],
            id_token="mobile-id-profile-sub",
            access_token="mobile-id-profile-access",
            jwks_uri="https://mts.example/jwks",
            provider=provider,
        ),
        db_session,
    )

    assert result["status"] == "verified"
    assert provider.notification_profile_fields == {
        "phone_number": "+76662150214",
        "birthdate": date(1990, 1, 1),
        "family_name": "Иванов",
        "given_name": "Иван",
        "middle_name": "Иванович",
    }
    assert provider.kyc_notification_calls == 1


async def test_public_callbacks_are_idempotent(
    db_session: AsyncSession,
) -> None:
    provider = LocalMobileIdProvider()
    user = User(
        phone="+76662150212",
        email="mobile-id-callback@test.local",
        name="Mobile ID Callback",
        role="client",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()

    started = await handle_start_identity_verification(
        StartIdentityVerificationCommand(
            user_id=user.id,
            birth_date=date(1992, 3, 4),
            provider=provider,
        ),
        db_session,
    )

    first_sms = await handle_mobile_id_sms_otp_notification(
        HandleMobileIdSmsOtpNotificationCommand(
            correlation_id=started["correlation_id"],
            auth_req_id="auth-callback",
            smsotp_endpoint="https://mts.example/sms",
        ),
        db_session,
    )
    second_sms = await handle_mobile_id_sms_otp_notification(
        HandleMobileIdSmsOtpNotificationCommand(
            correlation_id=started["correlation_id"],
            auth_req_id="auth-callback",
            smsotp_endpoint="https://mts.example/sms",
        ),
        db_session,
    )
    assert first_sms["id"] == second_sms["id"]
    assert second_sms["status"] == "sms_requested"

    first_notification = await handle_mobile_id_notification(
        HandleMobileIdNotificationCommand(
            correlation_id=started["correlation_id"],
            id_token="local-test-id-token",
            access_token="local-test-access-token",
            jwks_uri="https://mts.example/jwks",
            provider=provider,
        ),
        db_session,
    )
    second_notification = await handle_mobile_id_notification(
        HandleMobileIdNotificationCommand(
            correlation_id=started["correlation_id"],
            id_token="local-test-id-token",
            access_token="local-test-access-token",
            jwks_uri="https://mts.example/jwks",
            provider=provider,
        ),
        db_session,
    )
    assert first_notification["id"] == second_notification["id"]
    assert second_notification["status"] == "verified"
