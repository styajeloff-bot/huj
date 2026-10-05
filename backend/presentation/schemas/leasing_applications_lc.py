"""Pydantic schemas for LC-side leasing applications (Phase 5 E3)."""
from __future__ import annotations

import datetime as _dt
import uuid
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from presentation.schemas.applications import (
    ApplicationSummary,
    ApplicationVehicleRequest,
)

LcaStatus = Literal[
    "submitted",
    "under_review",
    "documents_required",
    "under_review_with_docs",
    "approved_scoring",
    "approved_scoring_another_cond",
    "rejected_prescoring",
    "approved_final",
    "approved_final_another_cond",
    "rejected_approved",
    "selected_lc",
    "deal",
    "closed",
]


class LcApplicationStatusUpdateRequest(BaseModel):
    """Express-compat dispatcher body for per-LC status updates."""

    model_config = ConfigDict(extra="ignore")

    status: Literal["approved", "rejected", "document_request"]
    comments: str | None = None
    requested_documents: list[str] = Field(default_factory=list)


class LcApplicationStatusUpdateResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    status: str


class CreateLcApplicationRequest(BaseModel):
    """POST /leasing-applications/ — LC creates application for client."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    company_id: UUID
    name: str = ""
    email: str = ""
    vehicles: list[ApplicationVehicleRequest] = Field(default_factory=list)
    selected_leasing_companies: list[UUID] = Field(
        default_factory=list, alias="selectedLeasingCompanies"
    )
    total_amount: Decimal | None = None
    down_payment: Decimal | None = None
    down_payment_percent: float | None = None
    lease_term_months: int | None = Field(default=None, ge=12, le=84)
    monthly_payment: Decimal | None = None
    total_cost: Decimal | None = None
    markup: Decimal | None = None
    rate: Decimal | None = None
    total_interest: Decimal | None = None
    buyout_amount: Decimal | None = None
    vat_refund: Decimal | None = None
    profit_tax_savings: Decimal | None = None
    total_savings: Decimal | None = None
    current_stage: str = "leasing_companies"
    questionnaire: dict[str, Any] | None = None
    vehicle_calculations: list[dict[str, Any]] | None = None


class UpdateLcApplicationRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str | None = None
    email: str | None = None
    total_amount: Decimal | None = None
    down_payment: Decimal | None = None
    down_payment_percent: float | None = None
    lease_term_months: int | None = Field(default=None, ge=12, le=84)
    monthly_payment: Decimal | None = None
    total_cost: Decimal | None = None
    markup: Decimal | None = None
    rate: Decimal | None = None
    total_interest: Decimal | None = None
    buyout_amount: Decimal | None = None
    vat_refund: Decimal | None = None
    profit_tax_savings: Decimal | None = None
    total_savings: Decimal | None = None
    selected_leasing_companies: list[UUID] | None = None
    current_stage: str | None = None


class LcApplicationsListResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    applications: list[ApplicationSummary]
    pagination: dict[str, int]


class LcApplicationCreateResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    application_id: uuid.UUID
    status: str
    application_ids: list[uuid.UUID] | None = Field(
        default=None, alias="applicationIds"
    )
    vehicles_reserved: int | None = Field(default=None, alias="vehiclesReserved")
    message: str | None = None


class LcApplicationUpdateResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    message: str
    application: dict[str, Any]


class LcApplicationSubmitResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    message: str
    application: dict[str, Any]


# ---------------------------------------------------------------------------
# Admin status change + status history (migrated from status_management —
# Phase 9 R3)
# ---------------------------------------------------------------------------


class ChangeLeasingAppStatusRequest(BaseModel):
    model_config = ConfigDict(
        extra="ignore", populate_by_name=True
    )

    internal_status: LcaStatus | None = Field(
        default=None,
        alias="internalStatus",
        description="Canonical per-LC status.",
    )
    change_reason: str | None = Field(
        default=None, alias="changeReason"
    )


class ChangeLeasingAppStatusResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    success: bool = True
    message: str
    link_id: UUID
    application_id: uuid.UUID
    leasing_company_id: UUID
    old_status: str | None = None
    new_status: str


class _StatusHistoryEntryOut(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: UUID
    entity_type: str
    entity_id: UUID
    old_status: str | None = None
    new_status: str
    changed_by: UUID | None = None
    comments: str | None = None
    changed_at: _dt.datetime | None = None


class LeasingAppStatusHistoryResponse(BaseModel):
    link_id: UUID
    application_id: uuid.UUID
    leasing_company_id: UUID
    history: list[_StatusHistoryEntryOut]
    total: int


class _LcApplicationLinkOut(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: UUID
    application_id: uuid.UUID
    leasing_company_id: UUID | None = None
    status: str | None = None
    review_notes: str | None = None


class LeasingApplicationsByApplicationResponse(BaseModel):
    """`GET /leasing-applications/by-application/:id` envelope."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    success: bool = True
    leasing_applications: list[_LcApplicationLinkOut] = Field(
        alias="leasingApplications"
    )
