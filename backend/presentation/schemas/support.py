"""Pydantic schemas for the admin support-program API."""

from __future__ import annotations

import datetime as _dt
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

SupportType = Literal[
    "down_payment_compensation",
    "vehicle_discount_dealer_compensation",
    "vehicle_discount_dealer_invoice",
    "leasing_interest_compensation",
]


class SupportParamsIn(BaseModel):
    """Loose container for type-specific support parameters (kept as JSONB)."""

    model_config = ConfigDict(extra="allow")

    value_type: Literal["amount", "percent"]
    value: float = Field(ge=0)
    min_amount: float | None = Field(default=None, ge=0)
    max_amount: float | None = Field(default=None, ge=0)
    min_percent: float | None = Field(default=None, ge=0, le=100)
    max_percent: float | None = Field(default=None, ge=0, le=100)
    compensation_period_months: int | None = Field(default=None, ge=1)
    start_month: int | None = Field(default=None, ge=1)


class CompensationTemplateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    payer: Literal["distributor", "dealer", "carcraft", "minpromtorg", "client"]
    recipient: Literal["leasing_company", "dealer", "carcraft", "client"]
    calculation_base: Literal[
        "base_price",
        "special_price",
        "dealer_cost",
        "application_price",
        "down_payment",
        "support_amount",
    ]
    value_type: Literal["percent", "sum"]
    value: float = Field(ge=0)
    min_amount: float | None = None
    max_amount: float | None = None
    min_percent: float | None = None
    max_percent: float | None = None
    payment_schedule_type: Literal[
        "fixed_date",
        "days_count",
        "weekly",
        "quarterly",
        "reporting_period",
    ] = "days_count"
    payment_schedule_period: (
        Literal[
            "week",
            "month",
            "two_months",
            "quarter",
            "half_year",
            "year",
        ]
        | None
    ) = None
    payment_schedule_value: str | None = None
    comment: str | None = Field(default="", max_length=1000)


# ---------------------------------------------------------------------------
# Support program — input
# ---------------------------------------------------------------------------


class SupportProgramRequest(BaseModel):
    """Create / update payload for a support program."""

    model_config = ConfigDict(extra="ignore")

    name: str = Field(min_length=1, max_length=255)
    mark_id: str | None = Field(default=None, max_length=50)
    mark_ids: list[str] = Field(default_factory=list)
    model_id: str | None = Field(default=None, max_length=50)
    model_ids: list[str] | None = None
    complectation_ids: list[str] | None = None
    vin: str | None = Field(default=None, max_length=50)
    vins: list[str] | None = None
    dealer_group_id: UUID | None = None
    dealer_group_ids: list[UUID] | None = None
    distributor_id: UUID | None = None
    distributor_ids: list[UUID] = Field(default_factory=list)
    leasing_company_ids: list[UUID] = Field(default_factory=list)
    support_type: SupportType
    support_params: SupportParamsIn
    production_year_from: int | None = Field(default=None, ge=1900, le=2100)
    production_year_to: int | None = Field(default=None, ge=1900, le=2100)
    production_date_from: _dt.date | None = None
    production_date_to: _dt.date | None = None
    delivery_date_from: _dt.date | None = None
    delivery_date_to: _dt.date | None = None
    starts_at: _dt.date | None = None
    ends_at: _dt.date | None = None
    is_active: bool = False
    is_compatible: bool = False
    compatible_support_ids: list[UUID] = Field(default_factory=list)
    show_to_leasing_company: bool = True
    show_to_client: bool = True
    comment: str | None = Field(default=None, max_length=5000)
    compensation_templates: list[CompensationTemplateIn] = Field(
        default_factory=list, max_length=4
    )


class AssignLeasingCompaniesRequest(BaseModel):
    leasing_company_ids: list[UUID] = Field(default_factory=list)


class SupportProgramPatchRequest(BaseModel):
    """Partial update payload for a support program.

    Currently supports flipping activity status (former
    `/activate` / `/deactivate` RPC endpoints).
    """

    model_config = ConfigDict(extra="ignore")

    active: bool | None = Field(
        default=None,
        validation_alias="active",
        serialization_alias="active",
    )
    is_active: bool | None = None


# ---------------------------------------------------------------------------
# Dealer group — input
# ---------------------------------------------------------------------------


class DealerGroupRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    distributor_company_id: UUID
    description: str | None = Field(default=None, max_length=1000)
    dealer_company_ids: list[UUID] = Field(default_factory=list, min_length=1)


class DealerGroupUpdateRequest(DealerGroupRequest):
    pass


# ---------------------------------------------------------------------------
# Output schemas (for OpenAPI; JSONResponse is not validated)
# ---------------------------------------------------------------------------


class PaginationOut(BaseModel):
    page: int
    limit: int
    total: int
    pages: int


class BillOfLadingFileOut(BaseModel):
    id: str
    bill_date: _dt.date | None = None
    file_name: str | None = None
    file_path: str | None = None
    file_size: int | None = None
    comment: str | None = None


class BillOfLadingOut(BaseModel):
    comment: str | None = None
    files: list[BillOfLadingFileOut] = Field(default_factory=list)


class SupportProgramOut(BaseModel):
    id: str
    name: str
    mark_id: str | None = None
    mark_ids: list[str] = Field(default_factory=list)
    mark_name: str | None = None
    model_id: str | None = None
    model_ids: list[str] = Field(default_factory=list)
    model_name: str | None = None
    complectation_ids: list[str] = Field(default_factory=list)
    vin: str | None = None
    vins: list[str] = Field(default_factory=list)
    dealer_group_id: str | None = None
    dealer_group_ids: list[UUID] = Field(default_factory=list)
    dealer_groups: list[dict[str, Any]] = Field(default_factory=list)
    distributor_id: str | None = None
    distributor_ids: list[UUID] = Field(default_factory=list)
    distributor_name: str | None = None
    distributors: list[dict[str, Any]] = Field(default_factory=list)
    leasing_company_ids: list[UUID] = Field(default_factory=list)
    leasing_companies: list[dict[str, Any]] = Field(default_factory=list)
    support_type: str
    support_params: dict[str, Any] = Field(default_factory=dict)
    production_year_from: int | None = None
    production_year_to: int | None = None
    production_date_from: _dt.date | None = None
    production_date_to: _dt.date | None = None
    delivery_date_from: _dt.date | None = None
    delivery_date_to: _dt.date | None = None
    starts_at: _dt.date | None = None
    ends_at: _dt.date | None = None
    is_active: bool = True
    status: str | None = None
    is_compatible: bool = False
    compatible_support_ids: list[UUID] = Field(default_factory=list)
    show_to_leasing_company: bool = True
    show_to_client: bool = True
    comment: str | None = None
    bill_of_lading: BillOfLadingOut | None = None
    compensation_templates: list[dict[str, Any]] = Field(default_factory=list)
    created_at: _dt.datetime | None = None
    updated_at: _dt.datetime | None = None


class SupportProgramListResponse(BaseModel):
    support_programs: list[SupportProgramOut]
    pagination: PaginationOut


class OrganizationSupportProgramListResponse(BaseModel):
    items: list[SupportProgramOut]
    pagination: PaginationOut


class SupportProgramResponse(BaseModel):
    support_program: SupportProgramOut
    message: str | None = None


class LeasingCompanyRefOut(BaseModel):
    id: str
    company_id: str | None = None


class LeasingCompaniesForProgramResponse(BaseModel):
    leasing_companies: list[LeasingCompanyRefOut]


class DealerRefOut(BaseModel):
    id: str
    name: str | None = None
    inn: str | None = None


class DealerGroupOut(BaseModel):
    id: str
    name: str
    description: str | None = None
    distributor_company_id: UUID
    distributor_id: UUID | None = None
    distributor: dict[str, Any] | None = None
    is_active: bool = True
    dealers_count: int = 0
    dealer_company_ids: list[UUID] = Field(default_factory=list)
    dealer_ids: list[UUID] = Field(default_factory=list)
    dealers: list[DealerRefOut] = Field(default_factory=list)
    created_by: UUID | None = None
    updated_by: UUID | None = None
    created_at: _dt.datetime | None = None
    updated_at: _dt.datetime | None = None


class DealerGroupResponse(BaseModel):
    dealer_group: DealerGroupOut
    message: str | None = None


class DealerGroupListResponse(BaseModel):
    dealer_groups: list[DealerGroupOut]
    pagination: PaginationOut


class MessageResponse(BaseModel):
    message: str


class BillOfLadingUploadResponse(BaseModel):
    message: str
    support_program: SupportProgramOut
    bill_of_lading: BillOfLadingFileOut
