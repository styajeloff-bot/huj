
"""Upload a new version of an existing document.

Marks every previous current row in the chain as ``is_current_version=False``
and inserts a new row with ``parent_document_id=root_id``,
``version=root.version + 1`` and ``review_status=pending``.
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.common import _isoformat
from domain.entities.document import Document, DocumentTypeConfig
from domain.errors import (
    CompanyNotFoundError,
    DocumentAccessDeniedError,
    DocumentNotFoundError,
)
from domain.services.object_storage import ObjectStorage
from infrastructure.messaging.dwh_events import emit_document_changed
from infrastructure.repositories import (
    document_types_repository as types_repo,
)
from infrastructure.repositories import (
    documents_repository as docs_repo,
)
from infrastructure.services.document_storage import build_company_key

_SAFE_FILENAME = re.compile(r"[^A-Za-z0-9._-]+")


def _safe_filename(original: str) -> str:
    name = original.strip().split("/")[-1].split("\\")[-1] or "file"
    return _SAFE_FILENAME.sub("_", name)[:120]


@dataclass
class UploadDocumentVersionCommand:
    actor_user_id: UUID
    actor_company_id: UUID | None
    parent_document_id: UUID
    file_filename: str
    file_content_type: str
    file_data: bytes
    related_application_id: uuid.UUID | None = None


async def handle_upload_document_version(
    cmd: UploadDocumentVersionCommand,
    session: AsyncSession,
    storage: ObjectStorage,
) -> dict:
    if cmd.actor_company_id is None:
        raise CompanyNotFoundError("Компания не привязана к пользователю")

    parent_dict = await docs_repo.get_by_id(
        session, cmd.parent_document_id
    )
    if parent_dict is None:
        raise DocumentNotFoundError(cmd.parent_document_id)
    parent = Document.from_dict(parent_dict)
    # Owner check — same company, or employee uploading on behalf of.
    if parent.company_id != cmd.actor_company_id:
        raise DocumentAccessDeniedError()

    type_row = await types_repo.get_by_type_code(
        session, parent.document_type
    )
    DocumentTypeConfig.from_dict(type_row)
    Document.ensure_allowed_file_type(
        cmd.file_content_type, type_row, filename=cmd.file_filename
    )
    Document.ensure_file_size_ok(len(cmd.file_data), type_row)

    safe = _safe_filename(cmd.file_filename)
    unique = f"{uuid.uuid4().hex[:8]}_v{parent.compute_next_version()}_{safe}"
    key = build_company_key(cmd.actor_company_id, unique)
    stored = await storage.put(key, cmd.file_data, cmd.file_content_type)

    root_id = parent.parent_id_for_new_version()
    new_version = parent.compute_next_version()
    new_id = await docs_repo.create_version(
        session,
        parent_document_id=root_id,
        company_id=cmd.actor_company_id,
        document_type=parent.document_type,
        file_name=unique,
        s3_key=key,
        file_path=stored,
        file_size=len(cmd.file_data),
        version=new_version,
        related_application_id=cmd.related_application_id
        or parent.related_application_id,
    )
    persisted = await docs_repo.get_by_id(session, new_id)
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
        "message": "Новая версия документа успешно загружена",
        "document": persisted,
    }
