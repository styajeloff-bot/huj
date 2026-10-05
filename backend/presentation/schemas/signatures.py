"""HTTP schemas for /api/v1/signatures/* and the invite endpoint."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Requests


class SignerInvitePayload(BaseModel):
    """One CEO / founder in the step-4 invite list."""

    model_config = ConfigDict(populate_by_name=True)
    signer_key: str = Field(alias="signerKey", min_length=1, max_length=255)
    full_name: str = Field(min_length=1, max_length=255)
    inn: str | None = Field(default=None, max_length=20)
    passport: str | None = Field(default=None, max_length=100)
    gender: Literal["male", "female"] | None = None
    # ``phone`` empty ⇒ physical-scan track.  The applicant owns the pending
    # SOPD signature request and uploads the wet-signed scan through the
    # canonical signature endpoint.
    phone: str | None = Field(default=None, max_length=20)


class InviteSignersRequest(BaseModel):
    company_id: UUID
    application_id: uuid.UUID | None = None
    signers: list[SignerInvitePayload] = Field(min_length=1)


# ---------------------------------------------------------------------------
# Responses


class SignerInviteResultOut(BaseModel):
    full_name: str
    phone: str | None = None
    user_id: UUID | None = None
    mode: Literal["electronic", "physical"]
    magic_link_sent: bool
    signature_request_ids: list[UUID] = Field(default_factory=list)


class InviteSignersResponse(BaseModel):
    results: list[SignerInviteResultOut]


class PassportRecognitionPreviewResponse(BaseModel):
    gender: Literal["male", "female"] | None = None
    gender_label: str | None = None
    birth_date: date | None = None
    full_name: str | None = None
    address: str | None = None


class PassportRecognitionUpdateResponse(PassportRecognitionPreviewResponse):
    signature_request_id: UUID
    passport_recognition_ids: dict[str, UUID]


class SopdPassportFieldsRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    fields: dict[str, Any]
    edited_fields: list[str] = Field(default_factory=list, max_length=12, alias="editedFields")


class SopdPassportSnapshotResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    application_id: UUID = Field(alias="applicationId")
    signer_key: str = Field(alias="signerKey")
    signature_request_id: UUID | None = Field(default=None, alias="signatureRequestId")
    fields: dict[str, Any]
    confidence: dict[str, int] | None = None
    show_confidence: bool = Field(alias="showConfidence")
    edited_fields: list[str] = Field(default_factory=list, alias="editedFields")
    name_mismatch: bool = Field(default=False, alias="nameMismatch")
    passport_files: list[dict[str, str]] = Field(default_factory=list, alias="passportFiles")
    has_unsaved_changes: bool = Field(alias="hasUnsavedChanges")
    actions_allowed: bool = Field(alias="actionsAllowed")


class SignatureRequestOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: UUID
    user_id: UUID
    application_id: uuid.UUID | None = None
    document_type: str
    status: str
    signature_method: str | None = None
    subject_snapshot: dict[str, Any]
    signed_pdf_s3_key: str | None = None
    sent_at: datetime | None = None
    signed_at: datetime | None = None
    revoked_at: datetime | None = None
    revoke_requested_at: datetime | None = None
    cancelled_at: datetime | None = None
    created_at: datetime
    sopd_operators: list[dict[str, Any]] = Field(default_factory=list)
    sopd_revoke_summary: dict[str, Any] | None = None


class SignatureListResponse(BaseModel):
    items: list[SignatureRequestOut]


class SignatureRevokeInitiatedResponse(BaseModel):
    message: str
    revoke_request_id: UUID
    phone_masked: str
    code_ttl_seconds: int
    resend_delay_seconds: int
    revoke_requested_at: datetime
    revoked_leasing_companies: list[dict[str, Any]] = Field(default_factory=list)
    revoked_contractors: list[dict[str, Any]] = Field(default_factory=list)
    excluded_contractors: list[dict[str, Any]] = Field(default_factory=list)
    is_full_revoke: bool = False


class SignatureRevokeOptionsResponse(BaseModel):
    leasing_companies: list[dict[str, Any]]
    contractors: list[dict[str, Any]]


class SignatureRevokeInitiateRequest(BaseModel):
    leasing_company_ids: list[UUID] = Field(min_length=1)


class SignatureRevokeVerifyRequest(BaseModel):
    code: str = Field(pattern=r"^\d{4}$")


class SignatureRevokeVerifiedResponse(BaseModel):
    message: str
    status: str
    revoke_request_id: UUID
    confirmed_at: datetime
    revoke_requested_at: datetime | None = None
    revoked_leasing_companies: list[dict[str, Any]] = Field(default_factory=list)
    revoked_contractors: list[dict[str, Any]] = Field(default_factory=list)
    excluded_contractors: list[dict[str, Any]] = Field(default_factory=list)
    is_full_revoke: bool = False
    document_s3_key: str
    revoke_document_download_url: str
