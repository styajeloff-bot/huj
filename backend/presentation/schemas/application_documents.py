"""Pydantic schemas for application-document requirements (shared by /leasing/document-requirements aliases)."""
from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Requirements — consumed by `/leasing/document-requirements` aliases after
# the Phase 15 cleanup of the `/application-documents/*` router.
# ---------------------------------------------------------------------------


class LcRequirementResponse(BaseModel):
    id: UUID
    leasing_company_id: UUID
    document_type_id: UUID
    document_type: str | None = None
    display_name: str | None = None
    description: str | None = None
    file_types: list[str] = Field(default_factory=list)
    max_file_size_mb: int | None = None
    auto_approve: bool | None = None
    validation_rules: dict[str, Any] | None = None
    is_required: bool
    is_mandatory: bool
    sort_order: int | None = None
    is_active: bool | None = None


class LcRequirementsSummary(BaseModel):
    total: int
    required: int
    mandatory: int
    auto_approve: int


class LeasingCompanyRef(BaseModel):
    id: UUID
    name: str | None = None


class ListLcRequirementsResponse(BaseModel):
    leasing_company: LeasingCompanyRef
    requirements: list[LcRequirementResponse]
    summary: LcRequirementsSummary


class UpdateRequirementItem(BaseModel):
    document_type: str | None = Field(
        default=None,
        description="type_code, если document_type_id не передан.",
    )
    document_type_id: UUID | None = Field(
        default=None, description="ID типа документа."
    )
    is_required: bool = False
    is_mandatory: bool = False
    sort_order: int = 0


class UpdateRequirementsBody(BaseModel):
    requirements: list[UpdateRequirementItem] = Field(default_factory=list)


class UpdateRequirementsResponse(BaseModel):
    message: str
    leasing_company_id: UUID
    updated_count: int
    deleted_count: int
