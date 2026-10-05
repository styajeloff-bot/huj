"""Pydantic schemas for document endpoints (Phase 4 D1)."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class DocumentResponse(BaseModel):
    id: UUID
    company_id: UUID
    document_type: str
    file_name: str | None = None
    user_title: str | None = None
    file_path: str | None = None
    file_size: int | None = None
    s3_key: str | None = None
    status: str | None = None
    leasing_company_status: str | None = None
    leasing_company_comments: str | None = None
    version: int | None = None
    parent_document_id: UUID | None = None
    is_current_version: bool | None = None
    related_application_id: uuid.UUID | None = None
    recognition_status: str | None = None
    recognition_error: str | None = None
    recognition_task_id: str | None = None
    uploaded_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class DocumentEnvelope(BaseModel):
    """Single-document write envelope returned by upload / version handlers."""

    message: str
    document: DocumentResponse | None = None
    application_id: uuid.UUID | None = None


class DocumentListResponse(BaseModel):
    documents: list[DocumentResponse]
    total: int


class DocumentVersionsResponse(BaseModel):
    versions: list[DocumentResponse]
    total: int


class DocumentForApplicationResponse(BaseModel):
    application_id: uuid.UUID
    documents: list[DocumentResponse]
    total: int


class DocumentRequirementResponse(BaseModel):
    document_type: str
    display_name: str | None = None
    description: str | None = None
    file_types: list[str] = Field(default_factory=list)
    max_file_size_mb: int | None = None
    auto_approve: bool | None = None
    validation_rules: dict[str, Any] | None = None
    is_required: bool
    is_mandatory: bool
    sort_order: int | None = None
    existing_document_id: UUID | None = None
    existing_status: str | None = None


class DocumentRequirementsResponse(BaseModel):
    application_id: uuid.UUID
    requirements: list[DocumentRequirementResponse]
    total: int


class DocumentRequestPartyResponse(BaseModel):
    id: UUID
    name: str


class DocumentRequestLinkedDocumentResponse(BaseModel):
    """Request attachment, identified by its application-document link."""

    id: UUID
    document_id: UUID
    file_name: str | None = None
    user_title: str | None = None
    file_size: int | None = None
    uploaded_at: datetime | None = None
    status: str | None = None
    download_url: str


class DocumentRequestItemResponse(BaseModel):
    id: UUID
    display_name: str
    slug: str
    status: str
    provided_at: datetime | None = None
    document: DocumentRequestLinkedDocumentResponse | None = None
    document_type: str
    has_form: bool = False
    form_schema: dict[str, Any] | None = None
    form_data: dict[str, Any] | None = None
    attachment: DocumentRequestLinkedDocumentResponse | None = None
    attachments: list[DocumentRequestLinkedDocumentResponse] = Field(default_factory=list)


class DocumentRequestBatchResponse(BaseModel):
    request_batch_id: UUID
    leasing_company: DocumentRequestPartyResponse
    comments: str | None = None
    requested_at: datetime | None = None
    requested_by: DocumentRequestPartyResponse | None = None
    items: list[DocumentRequestItemResponse] = Field(default_factory=list)


class DocumentRequestsResponse(BaseModel):
    application_id: UUID
    batches: list[DocumentRequestBatchResponse] = Field(default_factory=list)
    total: int


class ChangeDocumentStatusRequest(BaseModel):
    status: str = Field(
        ...,
        description=(
            "Целевой статус: pending, approved, rejected, revision_required."
        ),
    )
    comments: str | None = Field(
        default=None,
        description="Комментарий к смене статуса (опционально).",
    )


class ChangeDocumentStatusResponse(BaseModel):
    message: str
    document: DocumentResponse | None = None


# ---------------------------------------------------------------------------
# Phase 7a G2 backport — types / enhanced view / requirements / delete /
# restore / recognition / multi-upload
# ---------------------------------------------------------------------------


class DocumentTypeInfo(BaseModel):
    id: UUID
    name: str | None = None
    type_code: str | None = None
    display_name: str | None = None
    description: str | None = None
    is_required_for_all: bool | None = None
    file_types: list[str] = Field(default_factory=list)
    max_file_size_mb: int | None = None
    validation_rules: dict[str, Any] | None = None
    auto_approve: bool | None = None
    has_form: bool = False
    form_schema: dict[str, Any] | None = None


class DocumentTypesResponse(BaseModel):
    types: list[DocumentTypeInfo]
    total: int


class EnhancedRequirementResponse(BaseModel):
    document_type: str
    display_name: str | None = None
    description: str | None = None
    file_types: list[str] = Field(default_factory=list)
    max_file_size_mb: int | None = None
    auto_approve: bool | None = None
    validation_rules: dict[str, Any] | None = None
    is_required: bool
    is_mandatory: bool
    sort_order: int | None = None
    has_document: bool = False


class UserDocumentsEnhancedResponse(BaseModel):
    documents: list[DocumentResponse]
    requirements: list[EnhancedRequirementResponse]
    total: int


class UserRequirementResponse(BaseModel):
    document_type: str
    display_name: str | None = None
    description: str | None = None
    file_types: list[str] = Field(default_factory=list)
    max_file_size_mb: int | None = None
    auto_approve: bool | None = None
    validation_rules: dict[str, Any] | None = None
    is_required: bool
    is_mandatory: bool
    sort_order: int | None = None
    existing_document_id: UUID | None = None
    existing_status: str | None = None


class UserRequirementsResponse(BaseModel):
    requirements: list[UserRequirementResponse]
    total: int


class RequirementsByLcRequest(BaseModel):
    leasing_company_ids: list[UUID] = Field(
        ...,
        min_length=1,
        description="Список ID лизинговых компаний для агрегации требований.",
    )


class SoftDeleteDocumentResponse(BaseModel):
    message: str
    document_id: UUID


class RestoreDocumentResponse(BaseModel):
    message: str
    document: DocumentResponse | None = None


class ReprocessRecognitionResponse(BaseModel):
    message: str
    document: DocumentResponse | None = None
    recognition_scheduled: bool


class UploadDocumentsResponse(BaseModel):
    """Unified upload response — Phase 10 R4.

    Returned by ``POST /documents`` regardless of the upload flavour
    (single, multi-file batch, version, or upload-for-application). The
    optional ``application_id`` is populated when the upload was scoped
    to a particular leasing application via the M2M link.
    """

    documents: list[DocumentResponse]
    total: int
    application_id: uuid.UUID | None = None


# ---------------------------------------------------------------------------
# Status history (migrated from status_management schemas — Phase 9 R3)
# ---------------------------------------------------------------------------


class StatusHistoryEntryOut(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: UUID
    entity_type: str
    entity_id: UUID
    old_status: str | None = None
    new_status: str
    changed_by: UUID | None = None
    comments: str | None = None
    changed_at: datetime | None = None


class DocumentStatusHistoryResponse(BaseModel):
    document_id: UUID
    history: list[StatusHistoryEntryOut]
    total: int
