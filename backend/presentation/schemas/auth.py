"""Pydantic schemas for auth API (request + response)."""

from datetime import datetime

from pydantic import BaseModel, Field

from presentation.schemas.common import NonBlankAddress

# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------


class LoginRequest(BaseModel):
    phone: str = Field(pattern=r"^\+7\d{10}$")


class VerifyPhoneRequest(BaseModel):
    phone: str = Field(pattern=r"^\+7\d{10}$")
    code: str = Field(min_length=4, max_length=4, pattern=r"^\d{4}$")


class ResendCodeRequest(BaseModel):
    phone: str


class RegisterCompanyRequest(BaseModel):
    name: str
    inn: str = Field(pattern=r"^\d{10}$|^\d{12}$")
    kpp: str | None = None
    ogrn: str | None = None
    legal_address: NonBlankAddress | None = None
    actual_address: NonBlankAddress | None = None
    phone: str | None = None
    email: str | None = None
    manager_name: str | None = None
    entity_type: str | None = None
    full_name: str | None = None
    foundation_date: str | None = None
    employee_count: int | None = None
    business_activity: str | None = None
    website: str | None = None


class RegisterRequest(BaseModel):
    phone: str = Field(pattern=r"^\+7\d{10}$")
    email: str | None = None
    name: str | None = None
    companies: list[RegisterCompanyRequest] | None = None
    code: str | None = Field(
        default=None, min_length=4, max_length=4, pattern=r"^\d{4}$"
    )


class MagicConsumeRequest(BaseModel):
    """Body of POST /auth/magic/consume."""

    token: str = Field(min_length=1, max_length=64)


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class AvailableCompanyDto(BaseModel):
    id: str
    name: str
    inn: str | None = None
    role: str = "client"
    position_id: str | None = Field(default=None, alias="positionId")
    position_name: str | None = Field(default=None, alias="positionName")
    is_active: bool = Field(default=True, alias="isActive")
    model_config = {"populate_by_name": True}


class UserOut(BaseModel):
    id: str
    phone: str
    email: str | None = None
    name: str | None = None
    role: str | None = None
    scopes: list[str] = Field(default_factory=list)
    company_id: str | None = None
    sub_role: str | None = None
    can_view_applications: bool | None = Field(
        default=None, alias="canViewApplications"
    )
    can_create_applications: bool | None = Field(
        default=None, alias="canCreateApplications"
    )
    can_create_employees: bool | None = Field(
        default=None, alias="canCreateEmployees"
    )
    active_role: str | None = Field(default=None, alias="activeRole")
    active_company_id: str | None = Field(default=None, alias="activeCompanyId")
    active_company_name: str | None = Field(default=None, alias="activeCompanyName")
    position_id: str | None = Field(default=None, alias="positionId")
    position_name: str | None = Field(default=None, alias="positionName")
    available_companies: list[AvailableCompanyDto] = Field(
        default_factory=list, alias="availableCompanies"
    )
    model_config = {"populate_by_name": True}


class AuthResponse(BaseModel):
    """Returned after successful verification (verify-phone, register with code)."""

    message: str
    user: UserOut


class RegistrationPendingResponse(BaseModel):
    model_config = {"populate_by_name": True}

    message: str
    phone: str
    requires_verification: bool = Field(alias="requiresVerification")


class MeResponse(BaseModel):
    user: UserOut


class MessageResponse(BaseModel):
    message: str


# ---------------------------------------------------------------------------
# MFA request schemas
# ---------------------------------------------------------------------------


class MfaSetupVerifyRequest(BaseModel):
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


class MfaVerifyLoginRequest(BaseModel):
    model_config = {"populate_by_name": True}

    mfa_token: str = Field(alias="mfaToken")
    # Accept either a 6-digit TOTP or an alphanumeric backup code.
    code: str = Field(min_length=6, max_length=20)


class MfaDisableRequest(BaseModel):
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


# ---------------------------------------------------------------------------
# MFA response schemas
# ---------------------------------------------------------------------------


class MfaSetupResponse(BaseModel):
    model_config = {"populate_by_name": True}

    secret: str
    otpauth_url: str = Field(alias="otpauthUrl")
    qr_png_base64: str = Field(alias="qrPngBase64")


class MfaVerifySetupResponse(BaseModel):
    model_config = {"populate_by_name": True}

    message: str
    backup_codes: list[str] = Field(alias="backupCodes")


class MfaStepUpRequiredResponse(BaseModel):
    model_config = {"populate_by_name": True}

    mfa_required: bool = Field(default=True, alias="mfaRequired")
    mfa_token: str = Field(alias="mfaToken")
    message: str


class MfaSetupRequiredResponse(BaseModel):
    """Returned from verify-phone for privileged roles lacking MFA enrolment."""

    model_config = {"populate_by_name": True}

    mfa_setup_required: bool = Field(default=True, alias="mfaSetupRequired")
    setup_token: str = Field(alias="setupToken")
    message: str


class InitSetupRequest(BaseModel):
    """Mandatory-enrolment QR fetch — setup token only, no code yet."""

    model_config = {"populate_by_name": True}

    setup_token: str = Field(alias="setupToken")


class CompleteSetupRequest(BaseModel):
    model_config = {"populate_by_name": True}

    setup_token: str = Field(alias="setupToken")
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


class CompleteSetupResponse(BaseModel):
    model_config = {"populate_by_name": True}

    user: dict
    backup_codes: list[str] = Field(alias="backupCodes")


# ---------------------------------------------------------------------------
# Consolidated MFA (R8) — /auth/mfa with method-based dispatch
# ---------------------------------------------------------------------------


class MfaInitRequest(BaseModel):
    """Body for ``POST /auth/mfa`` (init setup).

    Accepts an optional ``setupToken`` for the half-session mandatory-
    enrolment flow. Omit it (or send ``null``) when the caller already
    holds a full access token — the endpoint then authenticates via the
    normal ``get_current_user`` path.
    """

    model_config = {"populate_by_name": True}

    setup_token: str | None = Field(default=None, alias="setupToken")


class MfaCompleteRequest(BaseModel):
    """Body for ``PUT /auth/mfa`` (complete setup)."""

    model_config = {"populate_by_name": True}

    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")
    setup_token: str | None = Field(default=None, alias="setupToken")


class MfaCompleteResponse(BaseModel):
    """Response from ``PUT /auth/mfa``.

    Either the authenticated-user activation shape (message + backupCodes)
    or the mandatory-enrolment full-login shape (user + backupCodes +
    cookies set by the router) — reflected as a union-ish Pydantic model.
    """

    model_config = {"populate_by_name": True}

    message: str | None = None
    user: dict | None = None
    backup_codes: list[str] = Field(alias="backupCodes")


class MfaStatusResponse(BaseModel):
    """Response from ``GET /auth/mfa``."""

    model_config = {"populate_by_name": True}

    enabled: bool
    method: str | None = None
    has_backup_codes: bool = Field(alias="hasBackupCodes")
    backup_codes_remaining: int | None = Field(
        default=None, alias="backupCodesRemaining"
    )


class MfaBackupCodesResponse(BaseModel):
    """Response from ``POST /auth/mfa/backup-codes``."""

    model_config = {"populate_by_name": True}

    backup_codes: list[str] = Field(alias="backupCodes")


# ---------------------------------------------------------------------------
# Session listing / revoke (F4/F5)
# ---------------------------------------------------------------------------


class SessionDto(BaseModel):
    """A single user session surfaced in the "active devices" UX."""

    model_config = {"populate_by_name": True}

    id: str
    ip_address: str | None = Field(default=None, alias="ipAddress")
    user_agent: str | None = Field(default=None, alias="userAgent")
    country_code: str | None = Field(default=None, alias="countryCode")
    created_at: datetime | None = Field(default=None, alias="createdAt")
    last_used_at: datetime | None = Field(default=None, alias="lastUsedAt")
    expires_at: datetime = Field(alias="expiresAt")
    is_current: bool = Field(default=False, alias="isCurrent")


class SessionListResponse(BaseModel):
    model_config = {"populate_by_name": True}

    sessions: list[SessionDto]


class ForceLogoutResponse(BaseModel):
    model_config = {"populate_by_name": True}

    revoked_count: int = Field(alias="revokedCount")


# Former AdminResetMfaRequest/Response moved to presentation.schemas.users
# as UserMfaResetBody / UserMfaResetResponse after Phase 11 R8 relocated
# the endpoint to DELETE /users/{user_id}/mfa.
