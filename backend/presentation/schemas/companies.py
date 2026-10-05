"""HTTP schemas for /api/v1/companies."""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import (
    AnyUrl,
    BaseModel,
    ConfigDict,
    Field,
    TypeAdapter,
    field_validator,
    model_validator,
)

from presentation.schemas.common import NonBlankAddress


class LeasingCompanyExtension(BaseModel):
    id: UUID
    company_id: UUID | None = None
    average_down_payment_percent: int | None = None
    average_lease_term_months: int | None = None
    average_markup_percent: float | None = None
    min_down_payment_percent: int | None = None
    max_lease_term_months: int | None = None
    special_offers: dict[str, Any] | None = None
    is_active: bool | None = None


class DistributorExtension(BaseModel):
    id: str
    company_id: str | None = None
    regions: dict[str, Any] | list[Any] | None = None
    brands: dict[str, Any] | list[Any] | None = None
    is_active: bool | None = None
    can_manage_dealer_groups: bool = False


CatalogBrandId = Annotated[str, Field(min_length=1, max_length=50)]


class DistributorBrandOut(BaseModel):
    id: CatalogBrandId
    name: str


class DistributorBrandsRequest(BaseModel):
    brand_ids: list[CatalogBrandId] = Field(default_factory=list)


class DistributorBrandsResponse(BaseModel):
    available_brands: list[DistributorBrandOut]
    selected_brand_ids: list[CatalogBrandId]


class DistributorInventoryBrandsResponse(BaseModel):
    brands: list[DistributorBrandOut]


class SopdSignerCandidate(BaseModel):
    key: str
    role: Literal["director_applicant", "director_management_company", "founder", "beneficiary", "representative"]
    role_label: str
    full_name: str
    inn: str | None = None
    share: str | None = None
    signing_method: Literal["sms", "file"]
    source: str
    sort_order: int


class CompanyProfile(BaseModel):
    """Flat company profile (post-010 schema, enrichment columns inline)."""

    id: str
    name: str
    inn: str | None = None
    kpp: str | None = None
    ogrn: str | None = None
    company_type: str
    legal_address: str | None = None
    actual_address: str | None = None
    phone: str | None = None
    email: str | None = None
    website: str | None = None
    is_active: bool | None = None
    full_name: str | None = None
    short_name: str | None = None
    okpo: str | None = None
    okato: str | None = None
    legal_form: str | None = None
    region: str | None = None
    city: str | None = None
    legal_address_details: dict[str, Any] | None = None
    registration_date: date | None = None
    registration_department: str | None = None
    employees_count: int | None = None
    main_okved_code: str | None = None
    main_okved_description: str | None = None
    additional_okved_code: str | None = None
    additional_okved_description: str | None = None
    additional_okved_list: list[Any] | dict[str, Any] | None = None
    director_full_name: str | None = None
    director_position: str | None = None
    director_inn: str | None = None
    founders: list[Any] | dict[str, Any] | None = None
    bank_bik: str | None = None
    bank_name: str | None = None
    bank_account_number: str | None = None
    authorized_capital: int | None = None
    net_profit: int | None = None
    reporting_year: int | None = None
    enrichment_status: str | None = None
    tax_system: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    leasing_company: LeasingCompanyExtension | None = None
    distributor: DistributorExtension | None = None


# ---------------------------------------------------------------------------
# Phase 7a — G4 additions
# ---------------------------------------------------------------------------

CompanyType = Literal["dealer", "leasing_company", "distributor", "other"]


class _CompanyActivationMutationForbidden(BaseModel):
    """Keep self-service profile writes from changing activation state."""

    @model_validator(mode="before")
    @classmethod
    def reject_is_active_mutation(cls, value: Any) -> Any:
        if isinstance(value, dict) and "is_active" in value:
            raise ValueError(
                "Поле is_active нельзя изменять напрямую; "
                "используйте DELETE /api/v1/companies/{id}"
            )
        return value


class CompaniesPagination(BaseModel):
    page: int
    limit: int
    total: int
    pages: int


class CompaniesListResponse(BaseModel):
    companies: list[CompanyProfile]
    pagination: CompaniesPagination


class UpsertCompanyProfileRequest(_CompanyActivationMutationForbidden):
    """Body for POST /api/v1/companies/profile."""

    model_config = ConfigDict(extra="ignore")

    name: str = Field(min_length=1, max_length=500)
    inn: str = Field(pattern=r"^\d{10}$|^\d{12}$")
    kpp: str | None = Field(default=None, pattern=r"^\d{9}$|^$")
    ogrn: str | None = Field(default=None, pattern=r"^\d{13}$|^\d{15}$|^$")
    company_type: CompanyType
    legal_address: NonBlankAddress = Field(max_length=1000)
    actual_address: NonBlankAddress | None = Field(default=None, max_length=1000)
    phone: str = Field(min_length=1, max_length=50)
    email: str = Field(min_length=3, max_length=255)
    website: str | None = Field(default=None, max_length=255)
    full_name: str | None = None
    short_name: str | None = None


class UpdateCompanyRequest(BaseModel):
    """Company update body; only ``carcraft_employee`` may send ``is_active``."""

    model_config = ConfigDict(extra="ignore")

    name: str | None = Field(default=None, max_length=500)
    inn: str | None = Field(default=None, pattern=r"^\d{10}$|^\d{12}$")
    kpp: str | None = Field(default=None)
    ogrn: str | None = Field(default=None)
    company_type: CompanyType | None = None
    legal_address: NonBlankAddress | None = Field(default=None, max_length=1000)
    actual_address: NonBlankAddress | None = Field(default=None, max_length=1000)
    phone: str | None = Field(default=None, max_length=50)
    email: str | None = Field(default=None, max_length=255)
    website: str | None = Field(default=None, max_length=255)
    full_name: str | None = None
    short_name: str | None = None
    is_active: bool | None = None
    can_manage_dealer_groups: bool | None = None


class AdminCompanyUpdateRequest(BaseModel):
    """Partial company update used exclusively by the admin companies API."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, max_length=500)
    company_type: CompanyType | None = None
    inn: str | None = Field(default=None, pattern=r"^\d{10}$|^\d{12}$")
    kpp: str | None = Field(default=None, pattern=r"^\d{9}$")
    ogrn: str | None = Field(default=None, pattern=r"^\d{13}$")
    is_active: bool | None = None
    phone: str | None = Field(default=None, pattern=r"^\+7\d{10}$")
    email: str | None = Field(
        default=None,
        max_length=255,
        pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
    )
    website: str | None = Field(default=None, max_length=255)
    legal_address: NonBlankAddress | None = Field(default=None, max_length=1000)
    actual_address: str | None = Field(default=None, max_length=1000)

    @field_validator(
        "name",
        "company_type",
        "inn",
        "kpp",
        "ogrn",
        "is_active",
        "legal_address",
        mode="before",
    )
    @classmethod
    def reject_null_for_required_fields(cls, value: Any) -> Any:
        """PATCH permits omitted required fields, but never an explicit null."""
        if value is None:
            raise ValueError("Поле не может быть null")
        return value

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("Название компании не может быть пустым")
        return value

    @field_validator("actual_address")
    @classmethod
    def validate_actual_address(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("Фактический адрес не может быть пустым; используйте null для очистки")
        return value

    @field_validator("website")
    @classmethod
    def validate_website(cls, value: str | None) -> str | None:
        if value is not None:
            TypeAdapter(AnyUrl).validate_python(value)
        return value

    @model_validator(mode="after")
    def validate_nonempty_payload(self) -> AdminCompanyUpdateRequest:
        if not self.model_fields_set:
            raise ValueError("Передайте хотя бы одно изменённое поле")
        return self


class AdminCompanyUpdateResponse(BaseModel):
    company: CompanyProfile


class CompanyTypeTransitionBlocker(BaseModel):
    """Safe aggregate dependency preventing a company-type transition."""

    code: str
    label: str
    count: int = Field(ge=1)
    resolution_hint: str


class AdminCompanyTypeTransitionConflictResponse(BaseModel):
    """Stable 409 response for a blocked administrative type transition."""

    detail: str
    code: Literal["TYPE_TRANSITION_CONFLICT"]
    field_errors: list[dict[str, Any]]
    blockers: list[CompanyTypeTransitionBlocker]


class CompanyChangeHistoryVersion(BaseModel):
    id: UUID
    changed_at: datetime
    actor_display_name: str
    action: Literal[
        "company_profile_saved",
        "company_status_changed",
        "distributor_brands_saved",
        "leasing_contractors_saved",
    ]
    snapshot: dict[str, Any]


class CompanyChangeHistoryPagination(BaseModel):
    next_cursor: str | None = None
    has_more: bool


class CompanyChangeHistoryResponse(BaseModel):
    items: list[CompanyChangeHistoryVersion]
    pagination: CompanyChangeHistoryPagination


class CompanyChangeHistoryComparisonResponse(BaseModel):
    base: CompanyChangeHistoryVersion
    target: CompanyChangeHistoryVersion
    diffs: list[dict[str, Any]]


class UpdateCompanyExternalDataRequest(BaseModel):
    """Body for PUT /api/v1/companies/{id}/external-data."""

    model_config = ConfigDict(extra="ignore")

    full_name: str | None = None
    short_name: str | None = None
    kpp: str | None = None
    ogrn: str | None = None
    okpo: str | None = None
    okato: str | None = None
    legal_address_details: dict[str, Any] | None = None
    registration_date: date | None = None
    registration_department: str | None = None
    employees_count: int | None = None
    main_okved_code: str | None = None
    main_okved_description: str | None = None
    additional_okved_code: str | None = None
    additional_okved_description: str | None = None
    additional_okved_list: list[Any] | dict[str, Any] | None = None
    director_full_name: str | None = None
    director_position: str | None = None
    director_inn: str | None = Field(default=None, pattern=r"^\d{12}$|^$")
    founders: list[Any] | dict[str, Any] | None = None
    bank_bik: str | None = Field(default=None, pattern=r"^\d{9}$|^$")
    bank_name: str | None = None
    bank_account_number: str | None = None
    authorized_capital: int | None = None
    net_profit: int | None = None
    reporting_year: int | None = None
    region: str | None = None
    city: str | None = None
    legal_form: str | None = None
    website: str | None = None
    enrichment_status: str | None = None


class UpsertCompanyProfileResponse(BaseModel):
    message: str
    company_id: str
    company: CompanyProfile


class UpdateCompanyResponse(BaseModel):
    message: str
    company: CompanyProfile


class DeactivateCompanyResponse(BaseModel):
    message: str
    company: CompanyProfile


class UpdateCompanyExternalDataResponse(BaseModel):
    message: str
    data: CompanyProfile


# ---------------------------------------------------------------------------
# Distributor-dealer link admin schemas
# ---------------------------------------------------------------------------


class DistributorDealersListResponse(BaseModel):
    dealers: list[CompanyProfile]
    pagination: CompaniesPagination


class LinkDistributorDealerRequest(BaseModel):
    dealer_company_id: UUID


class LinkDistributorDealerResponse(BaseModel):
    message: str
    dealer: CompanyProfile


class UnlinkDistributorDealerResponse(BaseModel):
    message: str


# ---------------------------------------------------------------------------
# SOPD contractors admin schemas
# ---------------------------------------------------------------------------


class ContractorLinkOut(BaseModel):
    id: UUID
    leasing_company_id: UUID
    leasing_company_company_id: UUID | None = None
    leasing_company_name: str | None = None
    leasing_company_inn: str | None = None
    contractor_id: UUID
    contractor_name: str
    contractor_inn: str
    created_at: datetime
    updated_at: datetime


class ContractorOut(BaseModel):
    id: UUID
    name: str
    inn: str
    created_at: datetime
    updated_at: datetime


class ContractorLinksListResponse(BaseModel):
    items: list[ContractorLinkOut]
    pagination: CompaniesPagination


class ContractorLinksResponse(BaseModel):
    items: list[ContractorLinkOut]


class ContractorListResponse(BaseModel):
    items: list[ContractorOut]
    pagination: CompaniesPagination


class CreateContractorRequest(BaseModel):
    contractor_name: str = Field(min_length=1, max_length=255)
    contractor_inn: str

    @field_validator("contractor_inn", mode="before")
    @classmethod
    def normalize_contractor_inn(cls, value: object) -> str:
        inn = "".join(ch for ch in str(value or "") if ch.isdigit())
        if len(inn) not in {10, 12}:
            raise ValueError("ИНН подрядчика должен содержать 10 или 12 цифр.")
        return inn


class CreateContractorResponse(BaseModel):
    contractor: ContractorOut
    created: bool


class CreateContractorLinkRequest(BaseModel):
    leasing_company_id: UUID
    contractor_name: str = Field(min_length=1, max_length=255)
    contractor_inn: str

    @field_validator("contractor_inn", mode="before")
    @classmethod
    def normalize_contractor_inn(cls, value: object) -> str:
        inn = "".join(ch for ch in str(value or "") if ch.isdigit())
        if len(inn) not in {10, 12}:
            raise ValueError("ИНН подрядчика должен содержать 10 или 12 цифр.")
        return inn


class CreateContractorLinkResponse(BaseModel):
    item: ContractorLinkOut
    contractor_created: bool
    link_created: bool


class UpdateContractorRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class UpdateContractorResponse(BaseModel):
    contractor: ContractorOut


class ContractorIdsRequest(BaseModel):
    contractor_ids: list[UUID]


class LeasingCompanyIdsRequest(BaseModel):
    leasing_company_ids: list[UUID]


class ContractorImportRowError(BaseModel):
    row: int
    message: str


class ContractorImportResponse(BaseModel):
    rows_total: int
    links_created: int
    links_skipped: int
    contractors_created: int
    errors: list[ContractorImportRowError]
