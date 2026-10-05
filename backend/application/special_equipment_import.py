"""Use cases for resumable special-equipment XLSX preview and application."""

from __future__ import annotations

import base64
import hashlib
import math
import re
import uuid
from collections import defaultdict
from collections.abc import AsyncIterable, Iterable
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from application.errors import ServiceError
from domain.special_equipment_import import (
    MAX_PARALLEL_PARTS,
    MAX_UI_ISSUES,
    PART_SIZE_BYTES,
    TERMINAL_STATUSES,
    ImportContractError,
    ImportErrorPolicy,
    ImportIssue,
    ImportMode,
    ImportStatus,
    IssueSeverity,
    ensure_can_apply,
    ensure_can_cancel,
    ensure_can_complete_upload,
    error_policy_for_mode,
    stable_request_hash,
    validate_job_contract,
)
from infrastructure.repositories import special_equipment_import_repository as repo
from infrastructure.services.special_equipment_import_storage import (
    ImportObjectStorage,
)
from infrastructure.services.special_equipment_xlsx import (
    JsonlRows,
    build_template_v8,
    build_template_v9,
)

_XLSX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
_DIGEST_RE = re.compile(r"^sha-256=:(?P<digest>[A-Za-z0-9+/=]+):$")


class ImportIssueCollector(list[ImportIssue]):
    """Bound validation diagnostics while preserving exact aggregate counts.

    A malformed multi-gigabyte workbook can contain millions of invalid rows.
    Keeping every diagnostic object in the Taskiq process would defeat the
    otherwise streaming XLSX/JSONL pipeline.  The collector stores only the
    UI-sized sample, while counters and invalid product identities cover the
    full input so ATOMIC/BEST_EFFORT decisions remain exact.
    """

    def __init__(self, *, sample_limit: int = MAX_UI_ISSUES) -> None:
        super().__init__()
        if sample_limit < 0:
            raise ValueError("sample_limit must not be negative")
        self.sample_limit = sample_limit
        self.total_count = 0
        self.error_count = 0
        self.warning_count = 0
        self.invalid_entity_external_keys: dict[str, set[str]] = defaultdict(set)
        self.invalid_product_external_keys = self.invalid_entity_external_keys[
            "product"
        ]

    @property
    def is_truncated(self) -> bool:
        return self.total_count > len(self)

    def append(self, issue: ImportIssue) -> None:
        self.total_count += 1
        if issue.severity is IssueSeverity.ERROR:
            self.error_count += 1
            if issue.entity_type and issue.external_key:
                self.invalid_entity_external_keys[issue.entity_type].add(
                    issue.external_key
                )
        else:
            self.warning_count += 1
        if len(self) < self.sample_limit:
            super().append(issue)

    def extend(self, issues: Iterable[ImportIssue]) -> None:
        for issue in issues:
            self.append(issue)


@dataclass(frozen=True)
class CreateImportCommand:
    requested_by: uuid.UUID
    idempotency_key: str
    filename: str
    size: int
    mode: ImportMode
    template_version: int
    target_warehouse_id: uuid.UUID | None = None


@dataclass(frozen=True)
class PutImportPartCommand:
    import_id: uuid.UUID
    requested_by: uuid.UUID
    part_number: int
    byte_start: int
    byte_end: int
    content_length: int
    content_digest: str
    chunks: AsyncIterable[bytes]


@dataclass(frozen=True)
class ApplyImportCommand:
    import_id: uuid.UUID
    requested_by: uuid.UUID
    if_match: str
    confirm_destructive_changes: bool


@dataclass(frozen=True)
class ImportTemplateArtifact:
    """Versioned template prepared for delivery by the HTTP adapter."""

    content: bytes
    digest: str
    filename: str


@lru_cache(maxsize=32)
def request_import_template(
    *, version: int, mode: ImportMode = ImportMode.APPEND
) -> ImportTemplateArtifact:
    """Build one supported template without leaking its implementation to HTTP."""

    if version == 9:
        content = build_template_v9(mode=mode)
    elif version == 8:
        content = build_template_v8(mode=mode)
    else:
        raise ServiceError("Unsupported template version", 422)
    filename = f"special-equipment-v{version}.xlsx"
    return ImportTemplateArtifact(
        content=content,
        digest=hashlib.sha256(content).hexdigest(),
        filename=filename,
    )


async def create_import(
    command: CreateImportCommand,
    session: AsyncSession,
    storage: ImportObjectStorage,
) -> tuple[dict[str, Any], bool]:
    try:
        validate_job_contract(
            filename=command.filename,
            size=command.size,
            mode=command.mode,
            template_version=command.template_version,
        )
    except ImportContractError as exc:
        raise ServiceError(str(exc), 422) from exc
    if not 8 <= len(command.idempotency_key) <= 200 or any(
        ord(character) < 33 or ord(character) > 126
        for character in command.idempotency_key
    ):
        raise ServiceError("Idempotency-Key is required", 422)
    if command.target_warehouse_id is not None and not await repo.warehouse_is_active(
        session, command.target_warehouse_id
    ):
        raise ServiceError("TARGET_WAREHOUSE_INVALID", 422)
    payload = {
        "filename": command.filename,
        "size": command.size,
        "mode": command.mode.value,
        "templateVersion": command.template_version,
        "targetWarehouseId": str(command.target_warehouse_id)
        if command.target_warehouse_id is not None
        else None,
    }
    request_hash = stable_request_hash(payload)
    await repo.acquire_create_idempotency_lock(
        session,
        requested_by=command.requested_by,
        idempotency_key=command.idempotency_key,
    )
    existing = await repo.get_job_by_idempotency(
        session,
        requested_by=command.requested_by,
        idempotency_key=command.idempotency_key,
    )
    if existing:
        if existing["request_hash"] != request_hash:
            raise ServiceError("IDEMPOTENCY_KEY_CONFLICT", 409)
        return await public_job(session, existing), True

    import_id = uuid.uuid4()
    source_key = f"special-equipment/imports/{import_id}/source.xlsx"
    try:
        upload_id = await storage.initiate_multipart(source_key, _XLSX_CONTENT_TYPE)
    except Exception as exc:
        raise ServiceError("Object storage is unavailable", 503) from exc
    expires_at = datetime.now(UTC) + timedelta(hours=24)
    error_policy = error_policy_for_mode(command.mode)
    try:
        job = await repo.create_job(
            session,
            values={
                "id": import_id,
                "requested_by": command.requested_by,
                "idempotency_key": command.idempotency_key,
                "request_hash": request_hash,
                # Kept as an internal technical value while the durable job table
                # retains the column. It is not part of the v2 API or identity.
                "source_code": "catalog_v2",
                "mode": command.mode.value,
                "error_policy": error_policy.value,
                "template_version": command.template_version,
                "target_warehouse_id": command.target_warehouse_id,
                "original_filename": command.filename,
                "expected_size_bytes": command.size,
                "source_object_key": source_key,
                "multipart_upload_id": upload_id,
                "upload_expires_at": expires_at,
                "retain_until": datetime.now(UTC) + timedelta(days=365),
            },
        )
    except repo.ImportTargetWarehouseUnavailableError as exc:
        with suppress(Exception):
            await storage.abort_multipart(key=source_key, upload_id=upload_id)
        raise ServiceError("WAREHOUSE_NOT_FOUND", 422) from exc
    return await public_job(session, job), False


async def list_imports(
    session: AsyncSession,
    *,
    requested_by: uuid.UUID,
    limit: int,
    before_created_at: datetime | None = None,
    before_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    rows = await repo.list_jobs(
        session,
        requested_by=requested_by,
        limit=min(max(limit, 1), 100) + 1,
        before_created_at=before_created_at,
        before_id=before_id,
    )
    has_more = len(rows) > min(max(limit, 1), 100)
    rows = rows[: min(max(limit, 1), 100)]
    next_cursor = None
    if has_more and rows:
        last = rows[-1]
        next_cursor = _encode_cursor(last["created_at"], last["id"])
    return {
        "items": await public_jobs(session, rows),
        "pagination": {"nextCursor": next_cursor, "hasMore": has_more},
    }


async def get_import(
    session: AsyncSession, *, import_id: uuid.UUID, requested_by: uuid.UUID
) -> dict[str, Any]:
    job = await repo.get_job(session, import_id, requested_by=requested_by)
    if job is None:
        raise ServiceError("Import not found", 404)
    return await public_job(session, job)


async def get_source_status(
    session: AsyncSession, *, import_id: uuid.UUID, requested_by: uuid.UUID
) -> dict[str, Any]:
    job = await repo.get_job(session, import_id, requested_by=requested_by)
    if job is None:
        raise ServiceError("Import not found", 404)
    parts = await repo.list_parts(session, job_id=import_id)
    return {
        "url": f"/api/v1/special-equipment/imports/{import_id}/source",
        "partsUrl": f"/api/v1/special-equipment/imports/{import_id}/source/parts",
        "contentUrl": (
            f"/api/v1/special-equipment/imports/{import_id}/source/content"
            if job["status"] != ImportStatus.AWAITING_UPLOAD.value
            else None
        ),
        "partSize": PART_SIZE_BYTES,
        "maxParallelParts": MAX_PARALLEL_PARTS,
        "bytesReceived": sum(int(part["size_bytes"]) for part in parts),
        "bytesTotal": int(job["expected_size_bytes"]),
        "receivedParts": [int(part["part_number"]) for part in parts],
        "expiresAt": job["upload_expires_at"],
        "completed": job["status"] != ImportStatus.AWAITING_UPLOAD.value,
    }


async def put_import_part(
    command: PutImportPartCommand,
    session: AsyncSession,
    storage: ImportObjectStorage,
) -> dict[str, Any]:
    if command.part_number <= 0:
        raise ServiceError("part_number must be positive", 422)
    job = await repo.get_job(
        session, command.import_id, requested_by=command.requested_by
    )
    if job is None:
        raise ServiceError("Import not found", 404)
    if job["status"] != ImportStatus.AWAITING_UPLOAD.value:
        raise ServiceError("Upload is already complete", 409)
    if job["upload_expires_at"] < datetime.now(UTC):
        raise ServiceError("Upload has expired", 410)

    expected_start = (command.part_number - 1) * PART_SIZE_BYTES
    expected_end = (
        min(
            expected_start + PART_SIZE_BYTES,
            int(job["expected_size_bytes"]),
        )
        - 1
    )
    expected_size = expected_end - expected_start + 1
    if (
        command.byte_start != expected_start
        or command.byte_end != expected_end
        or command.content_length != expected_size
    ):
        raise ServiceError("CONTENT_RANGE_MISMATCH", 422)
    digest = _parse_content_digest(command.content_digest)

    await repo.acquire_part_lock(
        session, job_id=command.import_id, part_number=command.part_number
    )
    existing = await repo.get_part(
        session, job_id=command.import_id, part_number=command.part_number
    )
    if existing:
        if (
            existing["sha256"] != digest
            or int(existing["byte_start"]) != command.byte_start
            or int(existing["byte_end"]) != command.byte_end
        ):
            raise ServiceError("PART_CHECKSUM_CONFLICT", 409)
        await repo.mark_part_retry(
            session, job_id=command.import_id, part_number=command.part_number
        )
        return _public_part(existing, idempotent=True)

    try:
        uploaded = await storage.put_part_stream(
            key=str(job["source_object_key"]),
            upload_id=str(job["multipart_upload_id"]),
            part_number=command.part_number,
            chunks=command.chunks,
            expected_size=expected_size,
            expected_sha256=digest,
            max_size=PART_SIZE_BYTES,
        )
    except ValueError as exc:
        raise ServiceError(str(exc), 422) from exc
    except Exception as exc:
        raise ServiceError("Object storage is unavailable", 503) from exc
    part = await repo.add_part(
        session,
        values={
            "job_id": command.import_id,
            "part_number": command.part_number,
            "byte_start": command.byte_start,
            "byte_end": command.byte_end,
            "size_bytes": uploaded.size_bytes,
            "sha256": uploaded.sha256,
            "storage_etag": uploaded.storage_etag,
            "status": "received",
        },
    )
    return _public_part(part, idempotent=False)


async def complete_import_upload(
    session: AsyncSession,
    storage: ImportObjectStorage,
    *,
    import_id: uuid.UUID,
    requested_by: uuid.UUID,
) -> dict[str, Any]:
    job = await repo.get_job(
        session, import_id, requested_by=requested_by, for_update=True
    )
    if job is None:
        raise ServiceError("Import not found", 404)
    try:
        ensure_can_complete_upload(str(job["status"]))
    except ImportContractError as exc:
        raise ServiceError(str(exc), 409) from exc
    if job["status"] == ImportStatus.UPLOADED.value:
        return await public_job(session, job)
    parts = await repo.list_parts(session, job_id=import_id)
    expected_parts = math.ceil(int(job["expected_size_bytes"]) / PART_SIZE_BYTES)
    if [part["part_number"] for part in parts] != list(range(1, expected_parts + 1)):
        raise ServiceError("UPLOAD_PARTS_MISSING", 409)
    if sum(int(part["size_bytes"]) for part in parts) != int(
        job["expected_size_bytes"]
    ):
        raise ServiceError("UPLOAD_SIZE_MISMATCH", 409)
    try:
        await storage.complete_multipart(
            key=str(job["source_object_key"]),
            upload_id=str(job["multipart_upload_id"]),
            parts=[
                (int(part["part_number"]), str(part["storage_etag"])) for part in parts
            ],
        )
        head = await storage.head(str(job["source_object_key"]))
    except Exception as exc:
        raise ServiceError("Object storage is unavailable", 503) from exc
    if head is None or head.size_bytes != int(job["expected_size_bytes"]):
        raise ServiceError("UPLOAD_SIZE_MISMATCH", 409)
    updated = await repo.update_job(
        session,
        import_id,
        status=ImportStatus.UPLOADED.value,
        phase="queued_for_validation",
        actual_size_bytes=head.size_bytes,
        uploaded_at=datetime.now(UTC),
    )
    return await public_job(session, updated)


async def request_import_application(
    command: ApplyImportCommand, session: AsyncSession
) -> dict[str, Any]:
    job = await repo.get_job(
        session,
        command.import_id,
        requested_by=command.requested_by,
        for_update=True,
    )
    if job is None:
        raise ServiceError("Import not found", 404)
    try:
        ensure_can_apply(
            str(job["status"]),
            str(job["preview_hash"]) if job["preview_hash"] else None,
            command.if_match,
        )
    except ImportContractError as exc:
        raise ServiceError(str(exc), 409) from exc
    if job["status"] in {
        ImportStatus.APPLYING.value,
        ImportStatus.COMPLETED.value,
        ImportStatus.COMPLETED_WITH_WARNINGS.value,
    }:
        return await public_job(session, job)
    summary = dict(job.get("summary") or {})
    requires_destructive_confirmation = bool(
        summary.get("requiresDestructiveConfirmation")
        or int(summary.get("destructiveCount") or 0)
    )
    if requires_destructive_confirmation and not command.confirm_destructive_changes:
        raise ServiceError("DESTRUCTIVE_CONFIRMATION_REQUIRED", 409)
    updated = await repo.update_job(
        session,
        command.import_id,
        status=ImportStatus.APPLYING.value,
        phase="queued_for_apply",
        accept_optional_image_failures=False,
        confirm_destructive_changes=command.confirm_destructive_changes,
    )
    return await public_job(session, updated)


async def cancel_import(
    session: AsyncSession,
    storage: ImportObjectStorage,
    *,
    import_id: uuid.UUID,
    requested_by: uuid.UUID,
) -> dict[str, Any]:
    job = await repo.get_job(
        session, import_id, requested_by=requested_by, for_update=True
    )
    if job is None:
        raise ServiceError("Import not found", 404)
    if job["status"] == ImportStatus.CANCELLED.value:
        return await public_job(session, job)
    try:
        ensure_can_cancel(str(job["status"]))
    except ImportContractError as exc:
        raise ServiceError(str(exc), 409) from exc
    if job["status"] == ImportStatus.AWAITING_UPLOAD.value:
        try:
            await storage.abort_multipart(
                key=str(job["source_object_key"]),
                upload_id=str(job["multipart_upload_id"]),
            )
        except Exception as exc:
            raise ServiceError("Object storage is unavailable", 503) from exc
    updated = await repo.update_job(
        session,
        import_id,
        cancellation_requested=True,
        status=ImportStatus.CANCELLED.value,
        phase="cancelled",
        cancelled_at=datetime.now(UTC),
    )
    return await public_job(session, updated)


async def get_preview(
    session: AsyncSession, *, import_id: uuid.UUID, requested_by: uuid.UUID
) -> dict[str, Any]:
    job = await repo.get_job(session, import_id, requested_by=requested_by)
    if job is None:
        raise ServiceError("Import not found", 404)
    if not job["preview_hash"]:
        raise ServiceError("Preview is not ready", 409)
    summary = dict(job.get("summary") or {})
    return {
        "importId": job["id"],
        "previewHash": job["preview_hash"],
        "catalogRevision": job["catalog_revision"],
        "summary": summary,
        "counts": summary.get("operationCounts", {}),
        "sheetRows": summary.get("rows", {}),
        "changes": summary.get("changes", []),
        "changesTotal": int(summary.get("changesTotal") or 0),
        "changesStored": int(summary.get("changesStored") or 0),
        "changesTruncated": bool(summary.get("changesTruncated")),
        "commerceImpact": summary.get("commerceImpact", {}),
        "imageSummary": summary.get(
            "imageSummary",
            {
                "requested": int(job.get("images_total") or 0),
                "transferred": int(job.get("images_done") or 0),
                "optionalFailures": int(summary.get("optionalImageFailures") or 0),
                "blockingFailures": int(summary.get("blockingImageFailures") or 0),
            },
        ),
        "destructiveCount": int(summary.get("destructiveCount") or 0),
        "destructivePercent": float(summary.get("destructivePercent") or 0),
        "requiresDestructiveConfirmation": bool(
            summary.get("requiresDestructiveConfirmation")
        ),
        "blockingIssues": (
            int(summary.get("errors") or 0)
            if job["error_policy"] == ImportErrorPolicy.ATOMIC.value
            else 0
        ),
        "warnings": int(summary.get("warnings") or 0)
        + (
            int(summary.get("errors") or 0)
            if job["error_policy"] == ImportErrorPolicy.BEST_EFFORT.value
            else 0
        ),
        "canApply": job["status"] == ImportStatus.PREVIEW_READY.value,
        "targetWarehouseId": job.get("target_warehouse_id"),
        "targetWarehouse": await repo.get_warehouse_assignment(
            session, job.get("target_warehouse_id")
        ),
    }


async def get_issues(
    session: AsyncSession,
    *,
    import_id: uuid.UUID,
    requested_by: uuid.UUID,
    severity: str | None,
    sheet_code: str | None,
    after_sequence: int,
    limit: int,
) -> dict[str, Any]:
    job = await repo.get_job(session, import_id, requested_by=requested_by)
    if job is None:
        raise ServiceError("Import not found", 404)
    rows = await repo.list_issues(
        session,
        job_id=import_id,
        severity=severity,
        sheet_code=sheet_code,
        after_sequence=max(after_sequence, 0),
        limit=min(max(limit, 1), 500) + 1,
    )
    page_size = min(max(limit, 1), 500)
    has_more = len(rows) > page_size
    rows = rows[:page_size]
    summary = dict(job.get("summary") or {})
    issues_total = int(job.get("issues_total") or 0)
    raw_issues_stored = summary.get("issuesStored")
    issues_stored = (
        raw_issues_stored
        if isinstance(raw_issues_stored, int)
        and not isinstance(raw_issues_stored, bool)
        else min(issues_total, MAX_UI_ISSUES)
    )
    return {
        "items": [public_issue(row) for row in rows],
        "total": issues_total,
        "stored": issues_stored,
        "truncated": bool(summary.get("issuesTruncated"))
        or issues_total > issues_stored,
        "pagination": {
            "nextSequence": rows[-1]["sequence"] if has_more and rows else None,
            "hasMore": has_more,
        },
    }


async def resolve_private_artifact(
    session: AsyncSession,
    *,
    import_id: uuid.UUID,
    requested_by: uuid.UUID,
    artifact: str,
) -> dict[str, Any]:
    job = await repo.get_job(session, import_id, requested_by=requested_by)
    if job is None:
        raise ServiceError("Import not found", 404)
    field = {
        "source": "source_object_key",
        "validation_report": "validation_report_key",
    }.get(artifact)
    if field is None or not job[field]:
        raise ServiceError("Artifact not found", 404)
    terminal_status_values = {status.value for status in TERMINAL_STATUSES}
    retain_until = job.get("retain_until")
    expired = (
        job.get("status") in terminal_status_values
        and retain_until is not None
        and retain_until <= datetime.now(UTC)
    )
    if job.get("artifact_cleanup_status") == "completed" or expired:
        # Once the retention deadline passes, the proxy stops serving the
        # artifact before the asynchronous delete. This gives callers stable
        # 410 semantics even when object-storage cleanup is temporarily slow.
        raise ServiceError("IMPORT_ARTIFACT_EXPIRED", 410)
    filename = (
        job["original_filename"]
        if artifact == "source"
        else f"special-equipment-import-{import_id}-validation.json"
    )
    content_type = _XLSX_CONTENT_TYPE if artifact == "source" else "application/json"
    return {
        "key": str(job[field]),
        "filename": str(filename),
        "content_type": content_type,
    }


async def public_jobs(
    session: AsyncSession, jobs: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    assignments = await repo.get_warehouse_assignments(
        session,
        {
            warehouse_id
            for job in jobs
            if (warehouse_id := job.get("target_warehouse_id")) is not None
        },
    )
    return [
        public_job_from_assignment(
            job,
            assignments.get(warehouse_id)
            if (warehouse_id := job.get("target_warehouse_id"))
            else None,
        )
        for job in jobs
    ]


async def public_job(session: AsyncSession, job: dict[str, Any]) -> dict[str, Any]:
    return public_job_from_assignment(
        job,
        await repo.get_warehouse_assignment(session, job.get("target_warehouse_id")),
    )


def public_job_from_assignment(
    job: dict[str, Any], target_warehouse: dict[str, Any] | None
) -> dict[str, Any]:
    import_id = job["id"]
    return {
        "id": import_id,
        "filename": job["original_filename"],
        "mode": job["mode"],
        "templateVersion": job["template_version"],
        "status": job["status"],
        "phase": job["phase"],
        "progress": {
            "bytes": {
                "done": job["actual_size_bytes"],
                "total": job["expected_size_bytes"],
            },
            "rows": {"done": job["rows_done"], "total": job["rows_total"]},
            "entities": {
                "done": job["entities_done"],
                "total": job["entities_total"],
            },
            "images": {
                "done": job["images_done"],
                "total": job["images_total"],
            },
        },
        "issuesTotal": job["issues_total"],
        "summary": job["summary"],
        "previewHash": job["preview_hash"],
        "catalogRevision": job["catalog_revision"],
        "appliedRevision": job["applied_revision"],
        "error": (
            {"code": job["error_code"], "detail": job["error_detail"]}
            if job["error_code"]
            else None
        ),
        "targetWarehouseId": job.get("target_warehouse_id"),
        "targetWarehouse": target_warehouse,
        "links": {
            "self": f"/api/v1/special-equipment/imports/{import_id}",
            "source": f"/api/v1/special-equipment/imports/{import_id}/source",
            "preview": f"/api/v1/special-equipment/imports/{import_id}/preview",
            "issues": f"/api/v1/special-equipment/imports/{import_id}/issues",
        },
        "createdAt": job["created_at"],
        "updatedAt": job["updated_at"],
    }


def public_issue(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "sequence": row["sequence"],
        "sheetCode": row["sheet_code"],
        "rowNumber": row["row_number"],
        "columnName": row["column_name"],
        "severity": row["severity"],
        "code": row["code"],
        "message": row["message"],
        "rawValuePreview": row["raw_value_preview"],
        "entityType": row["entity_type"],
        "entityCode": row["external_key"],
    }


def compute_preview_hash(
    *,
    source_sha256: str,
    catalog_revision: int,
    plan: dict[str, JsonlRows],
    expected_product_versions: dict[uuid.UUID, int],
    expected_active_seller_ids: set[uuid.UUID] | frozenset[uuid.UUID] = frozenset(),
    expected_modification_value_markers: (
        set[tuple[uuid.UUID, uuid.UUID]]
        | frozenset[tuple[uuid.UUID, uuid.UUID]]
    ) = frozenset(),
    expected_trim_value_markers: (
        set[tuple[uuid.UUID, uuid.UUID, uuid.UUID]]
        | frozenset[tuple[uuid.UUID, uuid.UUID, uuid.UUID]]
    ) = frozenset(),
) -> str:
    # Hash canonical JSONL files incrementally; never build a multi-million-row
    # JSON value in process memory.
    digest = hashlib.sha256()
    digest.update(source_sha256.encode("ascii"))
    digest.update(b"\0")
    digest.update(str(catalog_revision).encode("ascii"))
    digest.update(b"\0")
    for product_id, version in sorted(
        expected_product_versions.items(), key=lambda item: str(item[0])
    ):
        digest.update(str(product_id).encode("ascii"))
        digest.update(b":")
        digest.update(str(version).encode("ascii"))
        digest.update(b"\0")
    digest.update(b"active-sellers\0")
    for seller_id in sorted(expected_active_seller_ids, key=str):
        digest.update(str(seller_id).encode("ascii"))
        digest.update(b"\0")
    digest.update(b"modification-value-markers\0")
    for modification_id, attribute_id in sorted(
        expected_modification_value_markers,
        key=lambda marker: (str(marker[0]), str(marker[1])),
    ):
        digest.update(str(modification_id).encode("ascii"))
        digest.update(b":")
        digest.update(str(attribute_id).encode("ascii"))
        digest.update(b"\0")
    digest.update(b"trim-value-markers\0")
    for trim_id, modification_id, attribute_id in sorted(
        expected_trim_value_markers,
        key=lambda marker: (str(marker[0]), str(marker[1]), str(marker[2])),
    ):
        digest.update(str(trim_id).encode("ascii"))
        digest.update(b":")
        digest.update(str(modification_id).encode("ascii"))
        digest.update(b":")
        digest.update(str(attribute_id).encode("ascii"))
        digest.update(b"\0")
    for family in sorted(plan):
        digest.update(family.encode("ascii"))
        digest.update(b"\0")
        plan[family].close()
        with plan[family].path.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
    return digest.hexdigest()


def issues_to_rows(
    *, job_id: uuid.UUID, issues: list[ImportIssue]
) -> list[dict[str, Any]]:
    return [
        {
            "job_id": job_id,
            "sequence": index,
            **issue.as_dict(),
        }
        for index, issue in enumerate(issues[:MAX_UI_ISSUES], start=1)
    ]


def _parse_content_digest(value: str) -> str:
    match = _DIGEST_RE.fullmatch(value.strip())
    if not match:
        raise ServiceError("Content-Digest must use sha-256", 422)
    try:
        raw = base64.b64decode(match.group("digest"), validate=True)
    except ValueError as exc:
        raise ServiceError("Content-Digest is invalid", 422) from exc
    if len(raw) != hashlib.sha256().digest_size:
        raise ServiceError("Content-Digest is invalid", 422)
    return raw.hex()


def _public_part(part: dict[str, Any], *, idempotent: bool) -> dict[str, Any]:
    return {
        "partNumber": part["part_number"],
        "byteStart": part["byte_start"],
        "byteEnd": part["byte_end"],
        "size": part["size_bytes"],
        "digest": f"sha-256=:{base64.b64encode(bytes.fromhex(part['sha256'])).decode()}:",
        "received": True,
        "idempotent": idempotent,
    }


def _encode_cursor(created_at: datetime, entity_id: uuid.UUID) -> str:
    value = f"{created_at.isoformat()}|{entity_id}".encode()
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


def decode_cursor(value: str | None) -> tuple[datetime | None, uuid.UUID | None]:
    if not value:
        return None, None
    try:
        padded = value + "=" * (-len(value) % 4)
        raw = base64.urlsafe_b64decode(padded).decode()
        created, entity_id = raw.rsplit("|", 1)
        return datetime.fromisoformat(created), uuid.UUID(entity_id)
    except (ValueError, UnicodeDecodeError) as exc:
        raise ServiceError("Cursor is invalid", 422) from exc


# Durable upload/download use cases remain above; v2 owns normalization.
from application import special_equipment_import_v2 as _import_v2  # noqa: E402

build_normalized_plan = _import_v2.build_normalized_plan_v2
rebuild_summary_for_plan = _import_v2.rebuild_summary_for_plan
