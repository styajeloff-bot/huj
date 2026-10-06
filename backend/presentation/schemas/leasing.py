"""Pydantic schemas for the LC workflow API."""

from __future__ import annotations

import datetime as _dt
import uuid
from decimal import Decimal
from enum import Enum
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class LeasingCompanyOut(BaseModel):
    id: UUID
    company_id: UUID | None = None
    name: str | None = None
    inn: str | None = None
    average_down_payment_percent: int | None = None
    average_lease_term_months: int | None = None
    average_markup_percent: Decimal | None = None
    min_down_payment_percent: int | None = None
    max_lease_term_months: int | None = None
    is_active: bool = True


class LeasingCompaniesResponse(BaseModel):
    companies: list[LeasingCompanyOut]
    total: int


class LcApplicationLinkOut(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: UUID
    application_id: uuid.UUID | None = None
    leasing_company_id: UUID | None = None
    status: str | None = None
    display_status: str | None = None
    review_notes: str | None = None
    decision_comment: str | None = None
    response_pdf_file_name: str | None = None
    response_pdf_size: int | None = None
    response_pdf_uploaded_at: _dt.datetime | None = None
    submitted_at: _dt.datetime | None = None
    created_at: _dt.datetime | None = None
    updated_at: _dt.datetime | None = None


class LcApplicationSummary(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: uuid.UUID
    display_number: str | None = None
    company_id: UUID | None = None
    company_name: str | None = None
    company_inn: str | None = None
    name: str | None = None
    email: str | None = None
    status: str | None = None
    total_amount: Decimal | None = None
    monthly_payment: Decimal | None = None
    selected_leasing_companies: list[UUID] = Field(default_factory=list)
    vehicles_count: int = 0
    attached_documents_count: int = 0
    created_at: _dt.datetime | None = None
    updated_at: _dt.datetime | None = None


class LcApplicationRow(BaseModel):
    kind: Literal["application"] = "application"
    link: LcApplicationLinkOut
    application: LcApplicationSummary


class LcFastDealRow(BaseModel):
    """A fast-deal registration in the LC list: the flat ``FastDealListItem`` fields."""

    model_config = ConfigDict(extra="allow")

    kind: Literal["fast_deal"] = "fast_deal"
    id: uuid.UUID
    display_number: str
    source_type: Literal["dealer_to_leasing", "leasing_to_dealer"]
    status: str
    link_url: str


class Pagination(BaseModel):
    page: int = 1
    limit: int = 20
    total: int = 0
    pages: int = 0


class LcApplicationsListResponse(BaseModel):
    applications: list[LcApplicationRow | LcFastDealRow]
    pagination: Pagination


class LcRequirementOut(BaseModel):
    model_config = ConfigDict(extra="allow")

    document_type: str
    display_name: str | None = None
    description: str | None = None
    file_types: list[str] = Field(default_factory=list)
    max_file_size_mb: int | None = None
    auto_approve: bool | None = None
    validation_rules: dict[str, Any] | None = None
    is_required: bool = False
    is_mandatory: bool = False
    sort_order: int | None = None


class LcRequirementsResponse(BaseModel):
    requirements: list[LcRequirementOut]
    total: int


# ---------------------------------------------------------------------------
# Response workflow (proposals / PDF / decision)
# ---------------------------------------------------------------------------


class ProposalParams(BaseModel):
    """All params an LC can edit on a КП. All optional — incomplete КП are
    allowed in draft state, but Approve requires a fully populated one.
    """

    model_config = ConfigDict(extra="ignore")

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


class ProposalOut(ProposalParams):
    id: UUID
    leasing_company_application_id: UUID
    kind: str = "preliminary"
    position: int
    client_decision_action: str | None = None
    client_decision_at: _dt.datetime | None = None
    client_decision_comment: str | None = None
    pdf_file_name: str | None = None
    pdf_size: int | None = None
    pdf_uploaded_at: _dt.datetime | None = None
    created_at: _dt.datetime | None = None
    updated_at: _dt.datetime | None = None


class CreateProposalRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    prefill_from_application: bool = Field(
        default=False,
        description=(
            "Когда True — поля КП предзаполняются параметрами заявки клиента. "
            "Используется для первого КП в ответе ЛК."
        ),
    )


class ResponsePdfMetadata(BaseModel):
    file_name: str | None = None
    file_size: int | None = None
    uploaded_at: _dt.datetime | None = None


class LcResponseStateResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    link: LcApplicationLinkOut
    application: dict[str, Any] | None = None
    proposals: list[ProposalOut] = Field(default_factory=list)
    can_review: bool = False
    can_confirm_deal: bool = False
    confirm_deal_disabled_reason: str | None = None


class TakeInWorkResponse(BaseModel):
    application_id: UUID
    lca_id: UUID
    lca_status: str
    parent_status: str | None
    replayed: bool
    message: str


class DealDocumentType(str, Enum):
    SIGNED_LEASE_AGREEMENT = "signed_lease_agreement"
    ACCEPTANCE_TRANSFER_ACT = "acceptance_transfer_act"


class VehicleVinInput(BaseModel):
    vehicle_id: UUID
    vin: str = Field(..., min_length=1, max_length=50)


class DealDocumentInput(BaseModel):
    file_id: UUID
    document_type: DealDocumentType


class ConfirmDealRequest(BaseModel):
    deal_date: _dt.date
    vehicles: list[VehicleVinInput] = Field(default_factory=list)
    documents: list[DealDocumentInput] = Field(default_factory=list)


class ConfirmDealResponse(BaseModel):
    application_id: UUID
    leasing_company_application_id: UUID
    status: Literal["deal"]
    message: str
    replayed: bool
    special_equipment_orders: list[dict[str, Any]] = Field(default_factory=list)


class FinancialBundleResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    application_id: uuid.UUID
    questionnaire: dict[str, Any]
    accounting_report: dict[str, Any] | None = None


class AttachedDocumentOut(BaseModel):
    """One document attached to an application — for the LC «Прикреплённые
    документы» section. ``display_name`` is the Russian label fetched from
    ``document_types`` so the frontend doesn't need its own mapping."""

    model_config = ConfigDict(extra="allow")

    id: UUID
    document_type: str
    display_name: str
    period_label: str | None = None
    file_name: str | None = None
    file_size: int | None = None
    uploaded_at: _dt.datetime | None = None
    status: str | None = None
    leasing_company_status: str | None = None


class LcApplicationDocumentsResponse(BaseModel):
    application_id: uuid.UUID
    documents: list[AttachedDocumentOut]
    total: int


class ApproveApplicationDocumentRequest(BaseModel):
    status: Literal["approved"]


class ApproveApplicationDocumentResponse(BaseModel):
    application_id: UUID
    document_id: UUID
    leasing_company_id: UUID
    status: Literal["approved"]
    message: str


class UploadResponsePdfResponse(BaseModel):
    file_name: str
    file_size: int


class SubmitDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    action: Literal["approve", "reject"] = Field(..., description="Решение ЛК")
    kind: Literal["preliminary", "final"] = Field(
        default="final",
        description=(
            "Тип КП: preliminary — отправка предварительного расчёта "
            "(статус LCA → prescoring); final — финальное решение "
            "(approved/rejected)."
        ),
    )
    decision_comment: str | None = Field(
        default=None,
        description=("Комментарий ЛК к клиенту. Обязателен при action=reject."),
    )


class SubmitDecisionResponse(BaseModel):
    leasing_company_application_id: UUID
    leasing_company_id: UUID | None = None
    leasing_company_name: str | None = None
    application_id: uuid.UUID | None = None
    decision: str


class RequestedDocumentIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    source: Literal["catalog", "custom"]
    display_name: str = Field(min_length=1, max_length=255)
    document_type: str | None = Field(default=None, min_length=1, max_length=100)


class RequestDocumentsRequest(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    requested_documents: list[RequestedDocumentIn] = Field(
        alias="requestedDocuments",
        description=(
            "Список объектов с читаемым названием и slug. От 1 до 10 за один запрос."
        ),
        min_length=1,
        max_length=10,
    )
    comments: str | None = Field(default=None)


class RequestedDocumentOut(BaseModel):
    id: UUID
    display_name: str
    slug: str
    status: str
    requested_at: _dt.datetime | None = None


class RequestDocumentsResponse(BaseModel):
    success: bool = True
    message: str
    application_id: uuid.UUID
    leasing_company_id: UUID | None = None
    request_batch_id: UUID
    requested_documents: list[str] = Field(default_factory=list)
    items: list[RequestedDocumentOut] = Field(default_factory=list)


class ProposalDiffField(BaseModel):
    field: str
    requested: Any | None = None
    offered: Any | None = None
    changed: bool = False


class ClientProposalOut(ProposalOut):
    diff: list[ProposalDiffField] = Field(default_factory=list)


class ClientApprovalOfferLeasingCompanyOut(BaseModel):
    id: UUID | None = None
    name: str | None = None
    inn: str | None = None


class ClientApprovalOfferOut(BaseModel):
    model_config = ConfigDict(extra="allow")

    lca: LcApplicationLinkOut
    leasing_company: ClientApprovalOfferLeasingCompanyOut
    proposal: ClientProposalOut


class ClientApprovalOffersResponse(BaseModel):
    preliminary: list[ClientApprovalOfferOut] = Field(default_factory=list)
    final: list[ClientApprovalOfferOut] = Field(default_factory=list)


class ClientLeasingCompanyResponseOut(BaseModel):
    model_config = ConfigDict(extra="allow")

    leasing_company: dict[str, Any] | None = None
    decision: str | None = None
    decision_comment: str | None = None
    submitted_at: _dt.datetime | None = None
    response_pdf: ResponsePdfMetadata | None = None
    proposals: list[ClientProposalOut] = Field(default_factory=list)


class ClientLeasingResponsesResponse(BaseModel):
    application_id: uuid.UUID
    requested: dict[str, Any]
    responses: list[ClientLeasingCompanyResponseOut]
    approval_offers: ClientApprovalOffersResponse
