"""Pydantic schemas for compensations API."""
import uuid
from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Input schemas
# ---------------------------------------------------------------------------


class CompensationItemInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    payer: Literal["distributor", "dealer", "carcraft", "minpromtorg", "client"]
    recipient: Literal["leasing_company", "dealer", "carcraft", "client"]
    calculation_base: Literal[
        "base_price", "special_price", "dealer_cost",
        "application_price", "down_payment", "support_amount",
    ]
    calculation_base_amount: float | None = Field(default=None, ge=0)
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
    payment_schedule_period: Literal[
        "week",
        "month",
        "two_months",
        "quarter",
        "half_year",
        "year",
    ] | None = None
    payment_schedule_value: str | None = None
    comment: str | None = Field(default="", max_length=1000)


class CreateCompensationRequest(CompensationItemInput):
    applied_support_id: UUID
    application_id: uuid.UUID | None = None
    vehicle_id: UUID | None = None


class CreateBulkCompensationsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    applied_support_id: UUID
    application_id: uuid.UUID | None = None
    vehicle_id: UUID | None = None
    compensations: list[CompensationItemInput] = Field(min_length=1, max_length=4)


class UpdateCompensationStatusRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["accepted", "rejected", "paid", "cancelled"]
    paid_at: datetime | None = None
    documents: list[dict] | None = None
    reason: str | None = Field(default=None, max_length=2000)


class RecalculateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    applied_support_id: UUID


# ---------------------------------------------------------------------------
# Output schemas
# ---------------------------------------------------------------------------


class CompensationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    compensation_id: str
    applied_support_id: str
    applied_support_name: str | None = None
    support_program_id: str | None = None
    application_id: uuid.UUID | None = None
    application_display_number: str | None = None
    exchange_request_id: uuid.UUID | None = None
    exchange_request_display_number: str | None = None
    source: str = "platform"
    vehicle_id: str | None = None
    payer: str
    recipient: str
    calculation_base: str
    calculation_base_amount: float
    value_type: str
    value: float
    min_amount: float | None = None
    max_amount: float | None = None
    min_percent: float | None = None
    max_percent: float | None = None
    amount: float
    status: str
    payment_schedule_type: str
    payment_schedule_period: str | None = None
    payment_schedule_value: str | None = None
    due_date: date | None = None
    paid_at: datetime | None = None
    documents: list = Field(default_factory=list)
    acceptance_comment: str | None = None
    rejection_comment: str | None = None
    comment: str = ""
    created_by: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class PaginationOut(BaseModel):
    page: int
    limit: int
    total: int
    pages: int
    total_pages: int | None = None


class CompensationsListResponse(BaseModel):
    compensations: list[CompensationOut]
    pagination: PaginationOut


class CompensationResponse(BaseModel):
    compensation: CompensationOut


class CompensationDocumentUploadResponse(BaseModel):
    document: dict


class CompensationsResponse(BaseModel):
    compensations: list[CompensationOut]


class CancelCompensationsResponse(BaseModel):
    cancelled_count: int
    already_paid_count: int
    warnings: list[dict] = Field(default_factory=list)


class RecalculateResponse(BaseModel):
    compensations: list[CompensationOut]
