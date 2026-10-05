"""Pydantic schemas for the /api/v1/users domain."""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from presentation.schemas.common import NonBlankAddress


class CompanyDto(BaseModel):
    """Minimal company projection returned to the user."""

    id: str
    name: str
    inn: str | None
    role: str = "client"
    sub_role: str | None = None
    can_view_applications: bool = Field(default=False, alias="canViewApplications")
    can_create_applications: bool = Field(default=False, alias="canCreateApplications")
    position_id: str | None = Field(default=None, alias="positionId")
    position_name: str | None = Field(default=None, alias="positionName")
    is_active: bool = Field(default=True, alias="isActive")
    model_config = ConfigDict(populate_by_name=True)


class UserCompaniesResponse(BaseModel):
    companies: list[CompanyDto]


class AddCompanyPayload(BaseModel):
    """Pre-resolved company data, typically returned by /api/v1/company/search."""

    model_config = ConfigDict(extra="allow")

    name: str = Field(..., min_length=1)
    inn: Annotated[str, Field(pattern=r"^\d{10}$|^\d{12}$")]
    kpp: str | None = None
    ogrn: str | None = None
    legal_address: NonBlankAddress | None = None
    actual_address: NonBlankAddress | None = None
    phone: str | None = None
    email: str | None = None
    manager_name: str | None = None
    entity_type: str | None = None


class AddCompanyBody(BaseModel):
    company: AddCompanyPayload


class AddCompanyResponse(BaseModel):
    message: str
    company_id: str
    companies: list[CompanyDto]


class CompanySelectHistoryResponse(BaseModel):
    company_id: str | None
    updated_at: datetime | None = None


class SetCompanySelectHistoryBody(BaseModel):
    company_id: UUID = Field(...)


class SetCompanySelectHistoryResponse(BaseModel):
    company_id: str
    updated_at: datetime


# ---------------------------------------------------------------------------
# Sessions — consolidated /users/:id/sessions surface (R1)
# ---------------------------------------------------------------------------


class UserSessionDto(BaseModel):
    """One refresh-session row surfaced in the "active devices" UX."""

    model_config = ConfigDict(populate_by_name=True)

    id: str
    ip_address: str | None = Field(default=None, alias="ipAddress")
    user_agent: str | None = Field(default=None, alias="userAgent")
    country_code: str | None = Field(default=None, alias="countryCode")
    created_at: datetime | None = Field(default=None, alias="createdAt")
    last_used_at: datetime | None = Field(default=None, alias="lastUsedAt")
    expires_at: datetime | None = Field(default=None, alias="expiresAt")
    is_current: bool = Field(default=False, alias="isCurrent")


class UserSessionListResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    sessions: list[UserSessionDto]


class UserRevokeAllResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    revoked_count: int = Field(alias="revokedCount")


# ---------------------------------------------------------------------------
# Phone-change (self-only, moved from /client/phone-change/*)
# ---------------------------------------------------------------------------


_PHONE_PATTERN = r"^\+7\d{10}$"
_PHONE_CHANGE_CODE_PATTERN = r"^[0-9]{4}$"


class PhoneChangeRequestBody(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    new_phone: str = Field(alias="new_phone", pattern=_PHONE_PATTERN)


class PhoneChangeVerifyBody(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    new_phone: str = Field(alias="new_phone", pattern=_PHONE_PATTERN)
    code: str = Field(pattern=_PHONE_CHANGE_CODE_PATTERN)


class PhoneChangeMessageResponse(BaseModel):
    message: str


# ---------------------------------------------------------------------------
# DELETE /users/:id/mfa (admin-initiated reset, R8)
# ---------------------------------------------------------------------------


class UserMfaResetBody(BaseModel):
    """Body for ``DELETE /api/v1/users/{user_id}/mfa``.

    ``reason`` is a free-form audit string (usually a support ticket
    identifier) — captured verbatim on the emitted audit event, enforced
    minimum length to keep the trail meaningful.
    """

    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=3)


class UserMfaResetResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    message: str
    sessions_killed: int = Field(alias="sessionsKilled")


# ---------------------------------------------------------------------------
# /users/me — unified profile response + patch surface (R13a)
# Consolidates the former /client/profile, /dealer/profile,
# /distributor/profile endpoints into a single role-discriminated resource.
# ---------------------------------------------------------------------------


_ClientType = Literal["individual", "entrepreneur", "legal"]


class ClientProfileFields(BaseModel):
    """Role-specific projection for ``role == "client"``.

    Mirrors ``client_profiles`` + basic identity fields sourced via
    :func:`client_repository.get_profile_with_user`.
    """

    model_config = ConfigDict(extra="forbid")

    profile_id: str | None = None
    client_type: _ClientType | None = None
    passport_series: str | None = None
    passport_issued_date: date | None = None
    passport_issued_by: str | None = None
    company_name: str | None = None
    inn: str | None = None
    kpp: str | None = None
    ogrn: str | None = None
    legal_address: str | None = None
    address: str | None = None
    birth_date: date | None = None
    notification_settings: dict[str, Any] | None = None
    two_factor_enabled: bool | None = None
    phone_verified: bool | None = None
    identity_verified: bool | None = None
    identity_verified_at: datetime | None = None
    identity_verification_provider: str | None = None


class DealerCompanyFields(BaseModel):
    """Company block returned inside dealer ``role_specific``."""

    model_config = ConfigDict(extra="forbid")

    id: str | None = None
    name: str | None = None
    inn: str | None = None
    kpp: str | None = None
    ogrn: str | None = None
    legal_address: str | None = None
    actual_address: str | None = None
    phone: str | None = None
    email: str | None = None
    website: str | None = None
    company_type: str | None = None


class DealerSalesStatsFields(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total_clients: int = 0
    total_sales: int = 0
    total_revenue: float = 0.0
    total_applications: int = 0
    conversion_rate: float = 0.0


class DealerProfileFields(BaseModel):
    """Role-specific projection for ``role == "dealer"``.

    Bundles the dealer's company and aggregated sales stats.
    """

    model_config = ConfigDict(extra="forbid")

    company: DealerCompanyFields | None = None
    stats: DealerSalesStatsFields = Field(default_factory=DealerSalesStatsFields)


class DistributorExtensionFields(BaseModel):
    """Distributor extension row (``distributors`` table)."""

    model_config = ConfigDict(extra="forbid")

    id: str | None = None
    company_id: str | None = None
    regions: list[Any] | dict[str, Any] | None = None
    brands: list[Any] | dict[str, Any] | None = None
    is_active: bool | None = None


class DistributorProfileFields(BaseModel):
    """Role-specific projection for ``role == "distributor"``.

    Combines the distributor's company and their distributor extension row.
    """

    model_config = ConfigDict(extra="forbid")

    company: DealerCompanyFields | None = None
    distributor: DistributorExtensionFields | None = None


RoleSpecificProfile = (
    ClientProfileFields | DealerProfileFields | DistributorProfileFields | None
)


class UserMeResponse(BaseModel):
    """Unified response for ``GET /users/me``.

    Base identity fields from ``users`` + a discriminated ``role_specific``
    block whose shape is determined by the caller's role. For roles that
    don't own a role-specific extension (e.g. ``carcraft_employee``,
    ``leasing_company``) ``role_specific`` is ``None``.
    """

    model_config = ConfigDict(populate_by_name=True)

    id: str
    phone: str | None = None
    email: str | None = None
    name: str | None = None
    role: str | None = None
    company_id: str | None = None
    is_active: bool | None = None
    role_specific: RoleSpecificProfile = None


class ClientProfilePatch(BaseModel):
    """Partial update for ``role_specific`` when caller role is client."""

    model_config = ConfigDict(extra="forbid")

    client_type: _ClientType | None = None
    passport_series: str | None = None
    passport_issued_date: date | None = None
    passport_issued_by: str | None = None
    company_name: str | None = None
    inn: str | None = None
    kpp: str | None = None
    ogrn: str | None = None
    legal_address: str | None = None
    address: str | None = None
    birth_date: date | None = None
    notification_settings: dict[str, Any] | None = None


class DealerCompanyPatch(BaseModel):
    """Partial company-side update delivered via dealer ``role_specific``."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    inn: str | None = None
    kpp: str | None = None
    ogrn: str | None = None
    legal_address: NonBlankAddress | None = None
    actual_address: NonBlankAddress | None = None
    phone: str | None = None
    email: str | None = None
    website: str | None = None


class DealerProfilePatch(BaseModel):
    """Partial update for ``role_specific`` when caller role is dealer."""

    model_config = ConfigDict(extra="forbid")

    company: DealerCompanyPatch | None = None


class UserMePatchBody(BaseModel):
    """Body for ``PATCH /users/me``.

    Base user fields (``name`` / ``email``) are accepted at the top level;
    role-scoped fields live under ``role_specific`` and are validated
    against the caller's role by the handler. Sending a ``role_specific``
    block that doesn't match the caller's role → 422.

    Distributor self-update is intentionally not supported — the legacy
    ``PUT /distributor/profile`` endpoint didn't exist before either.
    """

    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    email: str | None = None
    role_specific: ClientProfilePatch | DealerProfilePatch | None = None


# ---------------------------------------------------------------------------
# Admin-scope CRUD on /users (R13b) — consolidated from /admin/users.
# ---------------------------------------------------------------------------


_ADMIN_ROLE_PATTERN = r"^(carcraft_employee|dealer|client|leasing_company|distributor)$"


class _AdminUserOut(BaseModel):
    id: str
    email: str | None = None
    phone: str
    name: str | None = None
    role: str | None = None
    company_id: str | None = None
    is_active: bool | None = None
    email_verified: bool | None = None
    last_login: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    company_name: str | None = None
    company_inn: str | None = None
    company_type: str | None = None


class _AdminUsersPagination(BaseModel):
    page: int
    limit: int
    total: int
    pages: int


class UsersListResponse(BaseModel):
    users: list[_AdminUserOut]
    pagination: _AdminUsersPagination


class UserCreateBody(BaseModel):
    """Body for ``POST /users`` — admin-create."""

    model_config = ConfigDict(extra="ignore")

    name: str | None = Field(default=None, max_length=255)
    email: str | None = Field(
        default=None, max_length=255, pattern=r"^$|^[^@\s]+@[^@\s]+\.[^@\s]+$"
    )
    phone: str = Field(pattern=r"^\+7\d{10}$")
    role: str = Field(pattern=_ADMIN_ROLE_PATTERN)
    company_id: UUID | None = None
    company: AddCompanyPayload | None = None
    is_active: bool = True
    email_verified: bool = True


class UserCreateResponse(BaseModel):
    user: _AdminUserOut
    message: str | None = None


class UserDeleteResponse(BaseModel):
    id: str
    message: str


class UserAdminPatchBody(BaseModel):
    """Body for ``PATCH /users/{user_id}`` — admin + self scope.

    R1 supported only ``status`` (mapped to ``is_active``). R13b extends
    this to cover the full admin-update payload (name / email / phone /
    role / company_id / ...).

    Self-scope callers (``user_id == me.id``) may only patch base fields
    (``name``, ``email``, ``phone``, ``company_id``);
    ``role`` and ``status`` / ``is_active`` / ``email_verified`` are
    admin-only.
    """

    model_config = ConfigDict(extra="forbid")

    # Admin-accepted status projection over ``is_active`` (R1 contract).
    status: Literal["active", "disabled"] | None = None
    # Direct is_active wire — admin-only; mutually exclusive with ``status``.
    is_active: bool | None = None
    # Base fields (both admin and self).
    name: str | None = Field(default=None, max_length=255)
    email: str | None = Field(
        default=None, max_length=255, pattern=r"^$|^[^@\s]+@[^@\s]+\.[^@\s]+$"
    )
    phone: str | None = Field(default=None, pattern=r"^\+7\d{10}$")
    company_id: UUID | None = None
    # Company object — admin can resolve a new company for a client.
    company: AddCompanyPayload | None = None
    # Admin-only fields.
    role: str | None = Field(default=None, pattern=_ADMIN_ROLE_PATTERN)
    email_verified: bool | None = None

    @model_validator(mode="after")
    def _company_xor_company_id(self) -> UserAdminPatchBody:
        if self.company is not None and self.company_id is not None:
            raise ValueError(
                "Укажите компанию только одним способом: "
                "company или company_id"
            )
        return self


class UserAdminPatchResponse(BaseModel):
    user: _AdminUserOut
    message: str | None = None


class UserAdminDetailResponse(BaseModel):
    """`GET /users/{id}` — admin single-user read."""

    user: _AdminUserOut


# ---------------------------------------------------------------------------
# Employee invitation & permission management
# ---------------------------------------------------------------------------


class InviteEmployeeRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    phone: str = Field(min_length=1, max_length=32)


class InviteEmployeeResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    message: str
    user_id: str


class CompanyMemberDto(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    user_id: str
    name: str | None = None
    phone: str | None = None
    sub_role: str | None = None
    can_view_applications: bool = Field(alias="canViewApplications")
    can_create_applications: bool = Field(alias="canCreateApplications")


class CompanyMembersResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    members: list[CompanyMemberDto]


class UpdatePermissionsRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    can_view_applications: bool | None = Field(
        default=None, alias="canViewApplications"
    )
    can_create_applications: bool | None = Field(
        default=None, alias="canCreateApplications"
    )


class UpdateSubRoleRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    sub_role: str = Field(pattern=r"^(administrator|manager|employee)$")
