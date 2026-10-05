from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True)
class IdentityVerificationStarted:
    auth_req_id: str
    phone_masked: str
    expires_at: datetime


@dataclass(frozen=True)
class IdentityVerificationData:
    mobile_id_sub: str
    matched: bool = True
    phone_number: str | None = None
    birthdate: date | None = None
    birthdate_match: str | None = None
    given_name: str | None = None
    middle_name: str | None = None
    family_name: str | None = None
    national_identifier_masked: str | None = None


class IdentityVerificationProvider(Protocol):
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
    ) -> IdentityVerificationStarted: ...

    async def submit_sms_code(
        self,
        *,
        auth_req_id: str | None,
        smsotp_endpoint: str | None,
        code: str,
        phone_number: str | None,
        birthdate: date | None,
    ) -> IdentityVerificationData: ...
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
    ) -> IdentityVerificationData: ...
