"""HTTP schemas for the special-equipment XLSX import resources."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ImportSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class CreateSpecialEquipmentImportRequest(ImportSchema):
    filename: str = Field(min_length=1, max_length=255)
    size: int = Field(gt=0)
    mode: Literal["APPEND", "PATCH", "FULL_SNAPSHOT"]
    template_version: Literal[8, 9] = Field(alias="templateVersion")
    target_warehouse_id: UUID | None = Field(default=None, alias="targetWarehouseId")


class ApplySpecialEquipmentImportRequest(ImportSchema):
    confirm_destructive_changes: bool = Field(
        default=False, alias="confirmDestructiveChanges"
    )


class ProgressCounter(ImportSchema):
    done: int = Field(ge=0)
    total: int | None = Field(default=None, ge=0)


class ImportProgress(ImportSchema):
    bytes: ProgressCounter
    rows: ProgressCounter
    entities: ProgressCounter
    images: ProgressCounter


class ImportErrorResponse(ImportSchema):
    code: str
    detail: str | None = None


class ImportLinks(ImportSchema):
    self: str
    source: str
    preview: str
    issues: str


class ImportWarehouseAssignment(ImportSchema):
    id: UUID
    address: str
    city_name: str | None = None


class SpecialEquipmentImportResponse(ImportSchema):
    id: UUID
    filename: str
    mode: Literal["APPEND", "PATCH", "FULL_SNAPSHOT"]
    template_version: int = Field(alias="templateVersion")
    status: str
    phase: str
    progress: ImportProgress
    issues_total: int = Field(alias="issuesTotal", ge=0)
    summary: dict[str, Any]
    preview_hash: str | None = Field(default=None, alias="previewHash")
    catalog_revision: int | None = Field(default=None, alias="catalogRevision")
    applied_revision: int | None = Field(default=None, alias="appliedRevision")
    error: ImportErrorResponse | None = None
    target_warehouse_id: UUID | None = Field(default=None, alias="targetWarehouseId")
    target_warehouse: ImportWarehouseAssignment | None = Field(
        default=None, alias="targetWarehouse"
    )
    links: ImportLinks
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")


class CursorPagination(ImportSchema):
    next_cursor: str | None = Field(default=None, alias="nextCursor")
    has_more: bool = Field(alias="hasMore")


class SpecialEquipmentImportListResponse(ImportSchema):
    items: list[SpecialEquipmentImportResponse]
    pagination: CursorPagination


class ImportSourceStatusResponse(ImportSchema):
    url: str
    parts_url: str = Field(alias="partsUrl")
    content_url: str | None = Field(default=None, alias="contentUrl")
    part_size: int = Field(alias="partSize", gt=0)
    max_parallel_parts: int = Field(alias="maxParallelParts", gt=0)
    bytes_received: int = Field(alias="bytesReceived", ge=0)
    bytes_total: int = Field(alias="bytesTotal", gt=0)
    received_parts: list[int] = Field(alias="receivedParts")
    expires_at: datetime = Field(alias="expiresAt")
    completed: bool


class ImportPartResponse(ImportSchema):
    part_number: int = Field(alias="partNumber", gt=0)
    byte_start: int = Field(alias="byteStart", ge=0)
    byte_end: int = Field(alias="byteEnd", ge=0)
    size: int = Field(gt=0)
    digest: str
    received: bool
    idempotent: bool


class ImportOperationCounts(ImportSchema):
    create: int = Field(ge=0)
    update: int = Field(ge=0)
    archive: int = Field(ge=0)
    remove: int = Field(ge=0)
    noop: int = Field(ge=0)
    rejected: int = Field(ge=0)


class ImportChangeSample(ImportSchema):
    entity_type: str = Field(alias="entityType")
    entity_code: str = Field(alias="entityCode")
    operation: str
    field: str | None = None
    before: str | int | float | bool | None = None
    after: str | int | float | bool | None = None


class ImportImageSummary(ImportSchema):
    requested: int = Field(ge=0)
    transferred: int = Field(ge=0)
    reused: int = Field(default=0, ge=0)
    optional_failures: int = Field(alias="optionalFailures", ge=0)
    blocking_failures: int = Field(alias="blockingFailures", ge=0)



class ImportPreviewResponse(ImportSchema):
    import_id: UUID = Field(alias="importId")
    preview_hash: str = Field(alias="previewHash")
    catalog_revision: int = Field(alias="catalogRevision", ge=0)
    summary: dict[str, Any]
    counts: dict[str, ImportOperationCounts]
    sheet_rows: dict[str, int] = Field(alias="sheetRows")
    changes: list[ImportChangeSample]
    changes_total: int = Field(alias="changesTotal", ge=0)
    changes_stored: int = Field(alias="changesStored", ge=0)
    changes_truncated: bool = Field(alias="changesTruncated")
    commerce_impact: dict[str, int] = Field(alias="commerceImpact")
    image_summary: ImportImageSummary = Field(alias="imageSummary")
    destructive_count: int = Field(alias="destructiveCount", ge=0)
    destructive_percent: float = Field(alias="destructivePercent", ge=0)
    requires_destructive_confirmation: bool = Field(
        alias="requiresDestructiveConfirmation"
    )
    blocking_issues: int = Field(alias="blockingIssues", ge=0)
    warnings: int = Field(ge=0)
    can_apply: bool = Field(alias="canApply")
    target_warehouse_id: UUID | None = Field(default=None, alias="targetWarehouseId")
    target_warehouse: ImportWarehouseAssignment | None = Field(
        default=None, alias="targetWarehouse"
    )


class ImportIssueResponse(ImportSchema):
    sequence: int = Field(gt=0)
    sheet_code: str = Field(alias="sheetCode")
    row_number: int | None = Field(default=None, alias="rowNumber")
    column_name: str | None = Field(default=None, alias="columnName")
    severity: Literal["error", "warning"]
    code: str
    message: str
    raw_value_preview: str | None = Field(default=None, alias="rawValuePreview")
    entity_type: str | None = Field(default=None, alias="entityType")
    entity_code: str | None = Field(default=None, alias="entityCode")


class IssueCursorPagination(ImportSchema):
    next_sequence: int | None = Field(default=None, alias="nextSequence")
    has_more: bool = Field(alias="hasMore")


class ImportIssuesResponse(ImportSchema):
    items: list[ImportIssueResponse]
    total: int = Field(ge=0)
    stored: int = Field(ge=0)
    truncated: bool
    pagination: IssueCursorPagination


class EmptyRequest(ImportSchema):
    """Explicit empty body for singleton resource creation."""


class ContentRange:
    def __init__(self, *, start: int, end: int, total: int) -> None:
        self.start = start
        self.end = end
        self.total = total

    @classmethod
    def parse(cls, value: str) -> ContentRange:
        if not value.startswith("bytes ") or "/" not in value or "-" not in value:
            raise ValueError("Content-Range must be bytes start-end/total")
        interval, total = value[6:].split("/", 1)
        start, end = interval.split("-", 1)
        parsed = cls(start=int(start), end=int(end), total=int(total))
        if parsed.start < 0 or parsed.end < parsed.start or parsed.total <= parsed.end:
            raise ValueError("Content-Range is invalid")
        return parsed


class IfMatchHeader(BaseModel):
    value: str

    @field_validator("value")
    @classmethod
    def strip_quotes(cls, value: str) -> str:
        normalized = value.strip()
        if normalized.startswith('W/"'):
            raise ValueError("Weak ETag is not accepted")
        if normalized.startswith('"') and normalized.endswith('"'):
            normalized = normalized[1:-1]
        if len(normalized) != 64:
            raise ValueError("If-Match must contain preview hash")
        return normalized
