"""Explicit UUID HTTP contracts for the registry."""
from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

DocumentType = Literal["contract", "agreement", "additional_agreement", "invoice", "act", "power_of_attorney", "other"]
DocumentStatus = Literal["active", "expiring", "expired", "pending", "deactivated"]


class StrictInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RelatedInput(StrictInput):
    platform_ml: bool | None = None
    leasing_company_ids: list[UUID] | None = None
    dealer_company_ids: list[UUID] | None = None
    distributor_company_ids: list[UUID] | None = None


class ParticipantsInput(StrictInput):
    platform_ml: bool = False
    leasing_company_ids: list[UUID] = Field(default_factory=list)
    dealer_company_ids: list[UUID] = Field(default_factory=list)
    distributor_company_ids: list[UUID] = Field(default_factory=list)
    mark_id: UUID | None = None
    model_id: UUID | None = None


class PeriodInput(StrictInput):
    valid_from: date
    valid_to: date | None = None

    @model_validator(mode="after")
    def valid_period(self) -> "PeriodInput":
        if self.valid_to is not None and self.valid_to < self.valid_from:
            raise ValueError("Дата окончания не может быть раньше начала")
        return self


class ChildInput(PeriodInput):
    document_type: DocumentType
    contract_number: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=255)
    related_companies: RelatedInput = Field(default_factory=RelatedInput)


class CreateInput(ChildInput):
    participants: ParticipantsInput


class VersionRelatedInput(StrictInput):
    platform_ml: bool
    leasing_company_ids: list[UUID]
    dealer_company_ids: list[UUID]
    distributor_company_ids: list[UUID]


class VersionInput(PeriodInput):
    expected_current_version_id: UUID
    name: str = Field(min_length=1, max_length=255)
    related_companies: VersionRelatedInput
    valid_to: date | None
    retained_file_ids: list[UUID] = Field(max_length=10)


class ActivateVersionInput(StrictInput):
    expected_current_version_id: UUID


class ActivationInput(StrictInput):
    active: bool


class ContextInput(StrictInput):
    leasing_company_id: UUID
    dealer_company_id: UUID | None = None
    distributor_company_id: UUID | None = None
    mark_id: UUID | None = None
    model_id: UUID | None = None
    platform_ml: bool = False


class CandidatesInput(StrictInput):
    program_id: UUID | None = None
    context: ContextInput | None = None

    @model_validator(mode="after")
    def exclusive_context(self) -> "CandidatesInput":
        if (self.program_id is None) == (self.context is None):
            raise ValueError("Укажите условие или контекст")
        return self


class Filters(StrictInput):
    document_type: DocumentType | None = None
    mark_id: UUID | None = None
    model_id: UUID | None = None
    valid_from: date | None = None
    valid_to: date | None = None
    status: DocumentStatus | None = None
    leasing_company_id: UUID | None = None
    dealer_company_id: UUID | None = None
    distributor_company_id: UUID | None = None
    participant_scope: Literal["participants", "related"] = "participants"
    search: str = Field("", max_length=255)

    @model_validator(mode="after")
    def valid_period(self) -> "Filters":
        if self.valid_from and self.valid_to and self.valid_from > self.valid_to:
            raise ValueError("Некорректный диапазон дат")
        return self


class CompanyOut(BaseModel):
    role: Literal["leasing_company", "dealer", "distributor"]
    company_id: UUID
    leasing_company_id: UUID | None = None
    name: str
    inn: str | None = None


class RelatedOut(BaseModel):
    platform_ml: bool
    leasing_company_ids: list[UUID]
    dealer_company_ids: list[UUID]
    distributor_company_ids: list[UUID]
    companies: list[CompanyOut]


class ParticipantsOut(RelatedOut):
    mark_id: UUID | None = None
    model_id: UUID | None = None
    mark_name: str | None = None
    model_name: str | None = None


class FileOut(BaseModel):
    id: UUID
    name: str
    type: str
    size: int
    download_url: str


class AuthorOut(BaseModel):
    id: UUID
    display_name: str


class VersionOut(BaseModel):
    id: UUID
    version_number: int
    name: str
    related_companies: RelatedOut
    is_current: bool
    metadata_backfilled: bool
    valid_from: date
    valid_to: date | None
    uploaded_by: AuthorOut
    uploaded_at: datetime
    files: list[FileOut]


class DocumentOut(BaseModel):
    id: UUID
    group_id: UUID
    is_main: bool
    document_type: DocumentType
    contract_number: str
    name: str
    related_companies: RelatedOut
    status: DocumentStatus
    active: bool
    current_version: VersionOut
    version_count: int


class GroupOut(BaseModel):
    group_id: UUID
    participants: ParticipantsOut
    main_document: DocumentOut | None
    display_document: DocumentOut
    children_count: int
    documents_count: int
    counts_by_type: dict[str, int]
    can_manage: bool


class PaginationOut(BaseModel):
    page: int
    page_size: int
    total: int


class GroupListOut(BaseModel):
    items: list[GroupOut]
    pagination: PaginationOut


class DocumentListOut(BaseModel):
    items: list[DocumentOut]
    pagination: PaginationOut


class HistoryOut(BaseModel):
    items: list[VersionOut]


class TypeOut(BaseModel):
    code: DocumentType
    name: str


class TypesOut(BaseModel):
    items: list[TypeOut]


class CompaniesOut(BaseModel):
    items: list[CompanyOut]


class CatalogItemOut(BaseModel):
    id: UUID
    name: str
    mark_id: UUID | None = None


class CatalogOut(BaseModel):
    items: list[CatalogItemOut]


class NumberAvailabilityOut(BaseModel):
    available: bool


class RelatedDocumentOut(BaseModel):
    id: UUID
    document_type: DocumentType
    contract_number: str
    label: str
    url: str


class TableRowOut(GroupOut, DocumentOut):
    related_documents: list[RelatedDocumentOut]


class CursorOut(BaseModel):
    has_more: bool
    next_cursor: str | None
    limit: int


class TableOut(BaseModel):
    items: list[TableRowOut]
    pagination: CursorOut


class CandidatesOut(BaseModel):
    items: list[DocumentOut]
    groups: list[GroupOut]


class ProgramUsageOut(BaseModel):
    id: UUID
    name: str


class UsagesOut(BaseModel):
    document_ids: list[UUID]
    programs: list[ProgramUsageOut]
    fingerprint: str
