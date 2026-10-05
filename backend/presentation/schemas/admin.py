"""Pydantic schemas for the admin CRUD / stats / applications API (F2)."""

from __future__ import annotations

import datetime as _dt
import uuid
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from presentation.schemas.common import NonBlankAddress

# ---------------------------------------------------------------------------
# Common
# ---------------------------------------------------------------------------


class PaginationOut(BaseModel):
    page: int
    limit: int
    total: int
    pages: int


class MessageResponse(BaseModel):
    message: str


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------


class UserCreateRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str | None = Field(default=None, max_length=255)
    email: str | None = Field(
        default=None, max_length=255, pattern=r"^$|^[^@\s]+@[^@\s]+\.[^@\s]+$"
    )
    phone: str = Field(pattern=r"^\+7\d{10}$")
    role: str = Field(
        pattern=r"^(carcraft_employee|dealer|client|leasing_company|distributor)$"
    )
    company_id: UUID | None = None
    is_active: bool = True
    email_verified: bool = True


class UserUpdateRequest(BaseModel):
    """All fields optional — only provided ones are updated."""

    model_config = ConfigDict(extra="ignore")

    name: str | None = Field(default=None, max_length=255)
    email: str | None = Field(
        default=None, max_length=255, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
    )
    phone: str | None = Field(default=None, pattern=r"^\+7\d{10}$")
    role: str | None = Field(
        default=None,
        pattern=r"^(carcraft_employee|dealer|client|leasing_company|distributor)$",
    )
    company_id: UUID | None = None
    is_active: bool | None = None
    email_verified: bool | None = None


class UserOut(BaseModel):
    id: UUID
    email: str | None = None
    phone: str
    name: str | None = None
    role: str | None = None
    company_id: UUID | None = None
    is_active: bool | None = None
    email_verified: bool | None = None
    last_login: _dt.datetime | None = None
    created_at: _dt.datetime | None = None
    updated_at: _dt.datetime | None = None
    company_name: str | None = None
    company_inn: str | None = None
    company_type: str | None = None


class UsersListResponse(BaseModel):
    users: list[UserOut]
    pagination: PaginationOut


class UserResponse(BaseModel):
    user: UserOut
    message: str | None = None


class UserDeleteResponse(BaseModel):
    id: UUID
    message: str


# ---------------------------------------------------------------------------
# Companies
# ---------------------------------------------------------------------------


class CompanyCreateRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    inn: str = Field(pattern=r"^\d{10}$|^\d{12}$")
    company_type: str = Field(pattern=r"^(dealer|leasing_company|distributor|other)$")
    name: str | None = Field(default=None, max_length=500)
    kpp: str | None = Field(default=None, max_length=20)
    ogrn: str | None = Field(default=None, max_length=20)
    legal_address: NonBlankAddress | None = Field(default=None, max_length=1000)
    phone: str | None = Field(default=None, max_length=50)
    email: str | None = Field(
        default=None, max_length=255, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
    )


class CompanyOut(BaseModel):
    id: UUID
    name: str
    inn: str | None = None
    kpp: str | None = None
    ogrn: str | None = None
    company_type: str
    legal_address: str | None = None
    phone: str | None = None
    email: str | None = None
    is_active: bool | None = None
    full_name: str | None = None
    short_name: str | None = None
    created_at: _dt.datetime | None = None
    updated_at: _dt.datetime | None = None


class CompanyResponse(BaseModel):
    company: CompanyOut
    message: str | None = None


# ---------------------------------------------------------------------------
# Leasing companies directory
# ---------------------------------------------------------------------------


class LeasingCompanyOut(BaseModel):
    id: UUID
    company_id: UUID | None = None
    name: str | None = None
    inn: str | None = None
    phone: str | None = None
    email: str | None = None
    is_active: bool = True
    average_down_payment_percent: int | None = None
    average_lease_term_months: int | None = None


class LeasingCompaniesListResponse(BaseModel):
    companies: list[LeasingCompanyOut]


# ---------------------------------------------------------------------------
# Dealers directory
# ---------------------------------------------------------------------------


class DealerOut(BaseModel):
    id: UUID
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    company_name: str | None = None
    company_inn: str | None = None


class DealersListResponse(BaseModel):
    dealers: list[DealerOut]


# ---------------------------------------------------------------------------
# Distributors directory
# ---------------------------------------------------------------------------


class DistributorOut(BaseModel):
    id: UUID
    company_id: UUID | None = None
    name: str | None = None
    inn: str | None = None
    phone: str | None = None
    email: str | None = None
    is_active: bool = True
    can_manage_dealer_groups: bool = False


class DistributorsListResponse(BaseModel):
    distributors: list[DistributorOut]


# ---------------------------------------------------------------------------
# Application vehicles (admin directory)
# ---------------------------------------------------------------------------


class AdminApplicationVehiclesListResponse(BaseModel):
    vehicles: list[dict]


# ---------------------------------------------------------------------------
# Warehouse brands distinct list
# ---------------------------------------------------------------------------


class WarehouseBrandsResponse(BaseModel):
    brands: list[str]


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


class AdminStatsResponse(BaseModel):
    users_by_role: dict[str, int]
    total_users: int
    companies_by_type: dict[str, int]
    total_companies: int
    applications_by_status: dict[str, int]
    total_applications: int
    total_applications_amount: Decimal
    total_vehicles: int


# ---------------------------------------------------------------------------
# Admin applications
# ---------------------------------------------------------------------------


class AdminApplicationOut(BaseModel):
    id: UUID
    display_number: str | None = None
    company_id: UUID | None = None
    company_name: str | None = None
    company_inn: str | None = None
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    status: str | None = None
    total_amount: Decimal | None = None
    down_payment: Decimal | None = None
    down_payment_percent: Decimal | None = None
    lease_term_months: int | None = None
    monthly_payment: Decimal | None = None
    selected_leasing_companies: list[UUID] = Field(default_factory=list)
    current_stage: str | None = None
    vehicles_count: int = 0
    total_vehicles_price: Decimal | None = None
    items_count: int = 0
    total_items_price: Decimal | None = None
    pending_price_items_count: int = Field(default=0, ge=0)
    can_assign_leasing_companies: bool = False
    created_at: _dt.datetime | None = None
    updated_at: _dt.datetime | None = None


class AdminApplicationsListResponse(BaseModel):
    applications: list[AdminApplicationOut]
    pagination: PaginationOut


class AdminSelectedCompanyOut(BaseModel):
    company_id: UUID
    company_name: str | None = None


class AdminApplicationVehiclePriceItemOut(BaseModel):
    type: str = "vehicle"
    id: UUID
    item_id: UUID | None = None
    vehicle_id: UUID | None = None
    title: str = "Автомобиль"
    image_url: str | None = None
    quantity: int = Field(default=1, ge=1)
    unit_price: Decimal | None = None
    catalog_price: Decimal | None = None
    discount_type: str | None = None
    discount_value: Decimal | None = None
    discount_amount: Decimal | None = None
    markup_type: str | None = None
    markup_value: Decimal | None = None
    markup_amount: Decimal | None = None
    final_price: Decimal | None = None
    show_catalog_price: bool = True
    total_price: Decimal | None = None
    dealer_comment: str | None = None
    currency_code: str = "RUB"
    status: str | None = None
    snapshot: dict[str, Any] | None = None


class AdminApplicationDetailApplicationOut(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: UUID
    display_number: str | None = None
    company_id: UUID | None = None
    company_name: str | None = None
    company_inn: str | None = None
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    status: str | None = None
    total_amount: Decimal | None = None
    down_payment: Decimal | None = None
    down_payment_percent: Decimal | None = None
    lease_term_months: int | None = None
    monthly_payment: Decimal | None = None
    current_stage: str | None = None
    vehicles_count: int = 0
    total_vehicles_price: Decimal | None = None
    items_count: int | None = None
    total_items_price: Decimal | None = None
    pending_price_items_count: int = Field(default=0, ge=0)
    can_assign_leasing_companies: bool = False
    items: list[dict[str, Any]] = Field(default_factory=list)
    vehicle_price_items: list[AdminApplicationVehiclePriceItemOut] = Field(
        default_factory=list
    )
    selected_leasing_companies: list[UUID] = Field(default_factory=list)
    selected_companies_info: list[AdminSelectedCompanyOut] = Field(default_factory=list)
    created_at: _dt.datetime | None = None
    updated_at: _dt.datetime | None = None


class AdminApplicationLeasingCompanyOut(BaseModel):
    id: UUID | None = None
    name: str | None = None
    inn: str | None = None


class AdminApplicationProposalOut(BaseModel):
    id: UUID
    leasing_company_application_id: UUID
    kind: str
    position: int
    total_amount: Decimal | None = None
    down_payment: Decimal | None = None
    down_payment_percent: Decimal | None = None
    lease_term_months: int | None = None
    monthly_payment: Decimal | None = None
    total_cost: Decimal | None = None
    markup: Decimal | None = None
    rate: Decimal | None = None
    total_interest: Decimal | None = None
    buyout_amount: Decimal | None = None
    vat_refund: Decimal | None = None
    profit_tax_savings: Decimal | None = None
    total_savings: Decimal | None = None
    client_decision_action: str | None = None
    client_decision_at: _dt.datetime | None = None
    client_decision_comment: str | None = None
    created_at: _dt.datetime | None = None
    updated_at: _dt.datetime | None = None


class AdminApplicationLcaDetailOut(BaseModel):
    id: UUID
    application_id: UUID | None = None
    leasing_company_id: UUID | None = None
    status: str | None = None
    review_notes: str | None = None
    decision_comment: str | None = None
    response_pdf_file_name: str | None = None
    response_pdf_size: int | None = None
    response_pdf_uploaded_at: _dt.datetime | None = None
    submitted_at: _dt.datetime | None = None
    created_at: _dt.datetime | None = None
    updated_at: _dt.datetime | None = None
    leasing_company: AdminApplicationLeasingCompanyOut | None = None
    proposals: list[AdminApplicationProposalOut] = Field(default_factory=list)


class AdminApplicationDetailResponse(BaseModel):
    application: AdminApplicationDetailApplicationOut
    leasing_company_applications: list[AdminApplicationLcaDetailOut]


class AdminApplicationPriceChangeOut(BaseModel):
    id: UUID
    item_id: UUID
    old_price: Decimal | None = None
    new_price: Decimal
    changed_by: UUID
    changed_by_name: str | None = None
    changed_at: _dt.datetime
    source: str


class AdminApplicationPriceChangesResponse(BaseModel):
    items: list[AdminApplicationPriceChangeOut] = Field(default_factory=list)
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=200)
    offset: int = Field(ge=0)


class AssignLeasingCompaniesRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    leasing_company_ids: list[UUID] = Field(min_length=1)


class AssignLeasingCompaniesResponse(BaseModel):
    application_id: uuid.UUID
    leasing_company_ids: list[UUID]
    assigned_count: int
    new_links_count: int
    clone_application_ids: list[UUID] = []
    status: str
    message: str
