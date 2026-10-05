
"""Upload a single document for the current user's company.

The handler validates content-type / size against the per-type config,
puts the file in S3 under a deterministic key and inserts a row into
``documents``. If the document type is supported by the recognition
provider, recognition is scheduled fire-and-forget — the upload
does not block on it.
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.common import _isoformat
from application.document_recognition import (
    SessionFactory,
    schedule_recognition,
)
from domain.entities.document import (
    RECOGNIZED_DOCUMENT_TYPES,
    Document,
    DocumentTypeConfig,
)
from domain.errors import CompanyNotFoundError
from domain.services.object_storage import ObjectStorage
from infrastructure.messaging.dwh_events import emit_document_changed
from infrastructure.repositories import (
    document_types_repository as types_repo,
)
from infrastructure.repositories import (
    documents_repository as docs_repo,
)
from infrastructure.repositories import status_history_repository as hist_repo
from infrastructure.services.document_storage import build_company_key

_SAFE_FILENAME = re.compile(r"[^A-Za-z0-9._-]+")


def _safe_filename(original: str) -> str:
    name = original.strip().split("/")[-1].split("\\")[-1] or "file"
    return _SAFE_FILENAME.sub("_", name)[:120]


@dataclass
class UploadedDocumentFile:
    filename: str
    content_type: str
    data: bytes


@dataclass
class UploadDocumentCommand:
    actor_user_id: UUID
    actor_company_id: UUID | None
    document_type: str
    file: UploadedDocumentFile
    related_application_id: uuid.UUID | None = None


async def handle_upload_document(
    cmd: UploadDocumentCommand,
    session: AsyncSession,
    storage: ObjectStorage,
    *,
    session_factory: SessionFactory | None = None,
) -> dict:
    """Insert a new ``documents`` row after pushing the file to object storage.

    On a recognition-supported document type a background recognition task
    is scheduled. The handler returns immediately with the persisted
    document dict; recognition completion is asynchronous.
    """
    if cmd.actor_company_id is None:
        raise CompanyNotFoundError("Компания не привязана к пользователю")

    type_row = await types_repo.get_by_type_code(
        session, cmd.document_type
    )
    type_config = DocumentTypeConfig.from_dict(type_row)

    Document.ensure_allowed_file_type(
        cmd.file.content_type,
        type_row,
        filename=cmd.file.filename,
    )
    Document.ensure_file_size_ok(
        len(cmd.file.data),
        type_row,
    )

    safe = _safe_filename(cmd.file.filename)
    unique = f"{uuid.uuid4().hex[:8]}_{safe}"
    key = build_company_key(cmd.actor_company_id, unique)
    stored = await storage.put(key, cmd.file.data, cmd.file.content_type)

    auto_approve = bool(type_config.auto_approve) if type_config else False
    initial_review_status = "approved" if auto_approve else "pending"

    document_id = await docs_repo.create_document(
        session,
        company_id=cmd.actor_company_id,
        document_type=cmd.document_type,
        file_name=unique,
        s3_key=key,
        file_path=stored,
        file_size=len(cmd.file.data),
        related_application_id=cmd.related_application_id,
        review_status=initial_review_status,
    )
    if auto_approve:
        await hist_repo.append_document_status_history(
            document_id=document_id,
            old_status=None,
            new_status="approved",
            changed_by=cmd.actor_user_id,
            comments="auto-approved on upload",
        )

    # Outside-test path: schedule the background recognition task with an
    # isolated session so the request lifecycle is independent. Tests omit
    # the factory to assert synchronous behaviour.
    if (
        cmd.document_type in RECOGNIZED_DOCUMENT_TYPES
        and session_factory is not None
    ):
        schedule_recognition(
            document_id=document_id,
            user_id=cmd.actor_user_id,
            document_type=cmd.document_type,
            file_bytes=cmd.file.data,
            filename=safe,
            content_type=cmd.file.content_type,
            auto_approve=auto_approve,
            session_factory=session_factory,
        )

    persisted = await docs_repo.get_by_id(session, document_id)
    if persisted is not None:
        emit_document_changed({
            "document_id": persisted["id"],
            "company_id": persisted["company_id"],
            "document_type": persisted.get("document_type"),
            "file_path": persisted.get("file_path"),
            "file_name": persisted.get("file_name"),
            "file_size": persisted.get("file_size"),
            "s3_key": persisted.get("s3_key"),
            "period_label": persisted.get("period_label"),
            "comments": persisted.get("comments"),
            "is_required": persisted.get("is_required"),
            "status": persisted.get("status"),
            "version": persisted.get("version"),
            "parent_document_id": persisted.get("parent_document_id"),
            "is_current_version": persisted.get("is_current_version"),
            "related_application_id": str(persisted["related_application_id"]) if persisted.get("related_application_id") else None,
            "approved_by_leasing_company": persisted.get("approved_by_leasing_company"),
            "leasing_company_status": persisted.get("leasing_company_status"),
            "leasing_company_comments": persisted.get("leasing_company_comments"),
            "leasing_company_reviewed_at": _isoformat(persisted.get("leasing_company_reviewed_at")),
            "extracted_data": persisted.get("extracted_data"),
            "recognition_status": persisted.get("recognition_status"),
            "recognition_error": persisted.get("recognition_error"),
            "dbrain_task_id": persisted.get("dbrain_task_id"),
            "recognized_at": _isoformat(persisted.get("recognized_at")),
            "uploaded_at": _isoformat(persisted.get("uploaded_at")),
            "verified_at": _isoformat(persisted.get("verified_at")),
            "verified_by": persisted.get("verified_by"),
            "created_at": _isoformat(persisted.get("created_at")),
            "updated_at": _isoformat(persisted.get("updated_at")),
            "_deleted": False,
        })
    return {
        "message": "Документ успешно загружен",
        "document": persisted,
    }
