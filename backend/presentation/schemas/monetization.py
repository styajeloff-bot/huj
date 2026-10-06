"""HTTP contracts for the internal monetization module."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_serializer, model_validator

from presentation.schemas.document_registry import DocumentOut as ReferenceDocumentOut

Money = Annotated[Decimal, Field(max_digits=14, decimal_places=2, allow_inf_nan=False)]


class InputModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ParticipantInput(InputModel):
    local_id: str | None = Field(default=None, max_length=80)
    participant_type: str
    base_type: str
    calc_type: str
    value: Money
    min: Money | None = None
    max: Money | None = None
    vat_excluded: bool = False
    expense_ref: str | None = Field(default=None, max_length=80)


class SourceInput(InputModel):
    source_type: str
    expenses: list[ParticipantInput]
    incomes: list[ParticipantInput] = Field(default_factory=list)


class ProgramInput(InputModel):
    name: str = Field(min_length=1, max_length=255)
    leasing_company_id: UUID
    dealer_company_id: UUID | None = None
    distributor_company_id: UUID | None = None
    support_program_id: UUID | None = None
    brand: str | None = Field(default=None, max_length=100)
    model: str | None = Field(default=None, max_length=100)
    modification: str | None = Field(default=None, max_length=255)
    trim: str | None = Field(default=None, max_length=255)
    vin: str | None = Field(default=None, max_length=50)
    period_start: date
    period_end: date | None = None
    status: Literal["active", "inactive"] = "active"
    sources: list[SourceInput]
    reference_document_ids: list[UUID] = Field(default_factory=list, max_length=100)


class ReferenceDocumentsInput(InputModel):
    document_ids: list[UUID] = Field(max_length=100)


class ReferenceDocumentsOut(BaseModel):
    items: list[ReferenceDocumentOut]


class ProgramStatusInput(InputModel):
    status: Literal["active", "inactive"]


class RevisionInput(InputModel):
    revision: int = Field(ge=1)


class AdjustmentItem(InputModel):
    deal_participant_amount_id: UUID
    input_mode: Literal["percent", "amount"] = "amount"
    new_value: Annotated[
        Decimal, Field(gt=0, max_digits=24, decimal_places=8, allow_inf_nan=False)
    ] | None = None
    new_percent: Annotated[
        Decimal, Field(gt=0, max_digits=38, decimal_places=8, allow_inf_nan=False)
    ] | None = None

    @model_validator(mode="after")
    def authoritative_input(self) -> Self:
        if self.input_mode == "percent":
            valid = self.new_percent is not None and self.new_value is None
        else:
            valid = self.new_value is not None and self.new_percent is None
        if not valid:
            raise ValueError("Передайте только значение выбранного способа ввода")
        return self


class AdjustmentInput(RevisionInput):
    items: list[AdjustmentItem]


class ConditionRequestInput(InputModel):
    leasing_company_ids: list[UUID] = Field(min_length=1, max_length=100)
    calc_type: Literal["percent", "amount"]
    value: Money


class ConditionResponseInput(InputModel):
    decision: Literal["accepted", "rejected", "countered"]
    counter_calc_type: Literal["percent", "amount"] | None = None
    counter_value: Money | None = None


class ConditionDecisionInput(InputModel):
    decision: Literal["accept_counter", "reject"]


class Pagination(BaseModel):
    page: int
    page_size: int
    total: int
    total_pages: int


class CompanyOption(BaseModel):
    id: UUID
    name: str
    inn: str | None = None


class DocumentOut(BaseModel):
    id: UUID
    file_name: str
    download_url: str
    uploaded_at: datetime | None = None
    uploaded_by_role: str | None = None
    revision: int | None = None
    outdated: bool = False


class SupportOption(BaseModel):
    id: UUID
    name: str


class SupportOut(SupportOption):
    documents: list[DocumentOut] = Field(default_factory=list)
    compatible_programs: list[SupportOption] = Field(default_factory=list)


class ParticipantSummary(BaseModel):
    participant_type: Literal["leasing", "dealer", "distributor", "platform"]
    company: CompanyOption | None = None


class ProgramSummary(BaseModel):
    id: UUID
    name: str
    brand: str | None = None
    period_start: date
    period_end: date | None = None
    status: str
    expense_participants: list[ParticipantSummary] = Field(default_factory=list)
    income_participants: list[ParticipantSummary] = Field(default_factory=list)


class ParticipantOut(ParticipantInput):
    model_config = ConfigDict(extra="ignore")
    id: UUID


class SourceOut(BaseModel):
    id: UUID
    source_type: str
    expenses: list[ParticipantOut]
    incomes: list[ParticipantOut]


class ProgramOut(ProgramSummary):
    rules_version: Literal[1, 2] = 1
    can_manage: bool
    leasing_company_id: UUID
    dealer_company_id: UUID | None = None
    distributor_company_id: UUID | None = None
    support_program_id: UUID | None = None
    model: str | None = None
    modification: str | None = None
    trim: str | None = None
    vin: str | None = None
    leasing_company: CompanyOption | None = None
    dealer: CompanyOption | None = None
    distributor: CompanyOption | None = None
    support_program: SupportOut | None = None
    sources: list[SourceOut]
    contracts: list[DocumentOut] = Field(default_factory=list)
    reference_documents: list[ReferenceDocumentOut] = Field(default_factory=list)
    created_at: datetime | None = None


class ProgramListOut(BaseModel):
    can_manage: bool
    items: list[ProgramSummary]
    pagination: Pagination


class AmountOut(BaseModel):
    id: UUID
    program_source_id: UUID | None = None
    source_participant_id: UUID | None = None
    side: str
    participant_type: str
    expense_ref_amount_id: UUID | None = None
    raw_amount: Decimal
    amount: Decimal
    clip: str
    applied_limit: Decimal | None = None
    vat_excluded: bool
    original_calc_type: Literal["percent", "amount"] | None = None
    original_percent: Decimal | None = None
    original_amount: Decimal
    percent: Decimal | None = None
    input_mode: Literal["percent", "amount"]
    base_type: Literal["property_value", "expense_amount"]
    calculation_base_amount: Decimal | None = None
    has_new_conditions: bool

    @field_serializer(
        "raw_amount", "amount", "original_percent", "original_amount", "percent",
        "calculation_base_amount", "applied_limit", when_used="json",
    )
    def plain_decimal(self, value: Decimal | None) -> str | None:
        return format(value, "f") if value is not None else None


class ConfirmationOut(BaseModel):
    applicable: bool
    confirmed_at: datetime | None = None
    confirmed_by: UUID | None = None
    confirmed_by_name: str | None = None


class DealOut(BaseModel):
    id: UUID
    application_number: str | None = None
    application_id: UUID | None = None
    leasing_company_application_id: UUID | None = None
    exchange_request_id: UUID | None = None
    fast_deal_id: UUID | None = None
    source_type: str
    brand: str | None = None
    program_id: UUID
    program_name: str | None = None
    leasing_company: CompanyOption | None = None
    dealer_company: CompanyOption
    distributor_company: CompanyOption | None = None
    client_company: CompanyOption | None = None
    base_amount: Decimal
    status: str
    revision: int
    expenses: list[AmountOut]
    incomes: list[AmountOut]
    can_adjust: bool
    has_new_conditions: bool
    can_confirm: bool
    can_upload_documents: bool
    confirmations: dict[str, ConfirmationOut]
    documents: list[DocumentOut]
    created_at: datetime | None = None

    @field_serializer("base_amount", when_used="json")
    def plain_base_amount(self, value: Decimal) -> str:
        return format(value, "f")


class DealSummary(BaseModel):
    id: UUID
    application_number: str | None = None
    fast_deal_id: UUID | None = None
    source_type: str
    brand: str | None = None
    leasing_company: CompanyOption | None = None
    dealer_company: CompanyOption
    distributor_company: CompanyOption | None = None
    client_company: CompanyOption | None = None
    base_amount: Decimal
    status: str
    confirmations: dict[str, ConfirmationOut]
    expense_participants: list[ParticipantSummary]
    income_participants: list[ParticipantSummary]
    created_at: datetime | None = None


class DealListOut(BaseModel):
    items: list[DealSummary]
    pagination: Pagination


class AdjustmentOut(DealOut):
    platform_auto_amount: Decimal
    confirmations_reset: bool


class DocumentListOut(BaseModel):
    documents: list[DocumentOut]


class CompanyLookupOut(BaseModel):
    items: list[CompanyOption]


class SupportLookupOut(BaseModel):
    items: list[SupportOption]


class ConditionRequestOut(BaseModel):
    application_number: str | None = None
    id: UUID
    application_id: UUID
    dealer_company_id: UUID
    leasing_company_id: UUID
    leasing_company: CompanyOption | None = None
    dealer_company: CompanyOption | None = None
    requested_calc_type: str
    requested_value: Decimal
    status: str
    counter_calc_type: str | None = None
    counter_value: Decimal | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ConditionRequestListOut(BaseModel):
    items: list[ConditionRequestOut]
    can_request: bool = False
    can_negotiate: bool = False


class ConditionRequestInboxOut(BaseModel):
    items: list[ConditionRequestOut]
    pagination: Pagination


class ConditionRequestCreatedOut(BaseModel):
    requests: list[ConditionRequestOut]
