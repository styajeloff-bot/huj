from __future__ import annotations

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class IdentityVerificationStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    verified: bool
    verified_at: datetime | None = None
    provider: str | None = None
    status: str | None = None
    failure_message: str | None = None
    verification_id: UUID | None = None
    expires_at: datetime | None = None


class StartIdentityVerificationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    birth_date: date | None = None


class IdentityVerificationAttemptResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    verification_id: UUID
    correlation_id: UUID
    status: str
    verified: bool
    verified_at: datetime | None = None
    provider: str
    phone_masked: str | None = None
    expires_at: datetime
    failure_message: str | None = None


class SubmitSmsCodeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(pattern=r"^\d{4,8}$")


class MobileIdDiagnosticsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    phone: str = Field(min_length=10, max_length=32)
    family_name: str = Field(min_length=1, max_length=255)
    given_name: str = Field(min_length=1, max_length=255)
    middle_name: str | None = Field(default=None, min_length=1, max_length=255)
    birth_date: date | None = None

    @field_validator("phone")
    @classmethod
    def _normalize_phone(cls, value: str) -> str:
        digits = "".join(ch for ch in value if ch.isdigit())
        if len(digits) == 10:
            digits = f"7{digits}"
        elif len(digits) == 11 and digits.startswith("8"):
            digits = f"7{digits[1:]}"
        if len(digits) != 11 or not digits.startswith("7"):
            raise ValueError("phone must be a Russian mobile phone number")
        return f"+{digits}"

    @field_validator("family_name", "given_name", "middle_name", mode="before")
    @classmethod
    def _strip_name(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        return value


class MobileIdDiagnosticsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    correlation_id: UUID
    status: Literal["sms_requested"]
    phone_masked: str
    expires_at: datetime
    provider: Literal["mobile_id"]


class MobileIdSmsOtpNotificationRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    correlation_id: UUID
    auth_req_id: str = Field(min_length=1, max_length=128)
    smsotp_endpoint: str = Field(min_length=1)
    send: dict[str, object] | None = None
    leading_kyc_match: bool | None = None


class MobileIdNotificationRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    correlation_id: UUID
    auth_req_id: str | None = None
    id_token: str = Field(min_length=1)
    access_token: str = Field(min_length=1)
    token_type: str | None = None
    expires_in: int | None = None
    jwks_uri: str | None = None
    leading_kyc_match: bool | None = None


class MobileIdCallbackResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID | None = None
    status: str
    detail: str | None = None
