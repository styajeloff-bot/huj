
"""Restore a previously soft-deleted document.

Marks ``is_current_version`` back to ``True`` and demotes any sibling
that was current in the meantime. Owner / employee only.
"""
from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.common import _isoformat
from domain.entities.document import Document
from domain.errors import DocumentNotFoundError
from infrastructure.messaging.dwh_events import emit_document_changed
from infrastructure.repositories import documents_repository as docs_repo
from infrastructure.repositories import status_history_repository as hist_repo


@dataclass
class RestoreDocumentCommand:
    document_id: UUID
    actor_user_id: UUID
    actor_role: str
    actor_company_id: UUID | None


async def handle_restore_document(
    cmd: RestoreDocumentCommand,
    session: AsyncSession,
) -> dict:
    raw = await docs_repo.get_by_id(session, cmd.document_id)
    if raw is None:
        raise DocumentNotFoundError(cmd.document_id)
    entity = Document.from_dict(raw)
    entity.ensure_owned_by(
        user_id=cmd.actor_user_id,
        role=cmd.actor_role,
        company_id=cmd.actor_company_id,
    )
    await docs_repo.restore(session, cmd.document_id)
    await hist_repo.append_document_status_history(
        document_id=cmd.document_id,
        old_status="deleted",
        new_status=entity.review_status,
        changed_by=cmd.actor_user_id,
        comments="restore",
    )
    restored = await docs_repo.get_by_id(session, cmd.document_id)
    if restored is not None:
        emit_document_changed({
            "document_id": restored["id"],
            "company_id": restored["company_id"],
            "document_type": restored.get("document_type"),
            "file_path": restored.get("file_path"),
            "file_name": restored.get("file_name"),
            "file_size": restored.get("file_size"),
            "s3_key": restored.get("s3_key"),
            "period_label": restored.get("period_label"),
            "comments": restored.get("comments"),
            "is_required": restored.get("is_required"),
            "status": restored.get("status"),
            "version": restored.get("version"),
            "parent_document_id": restored.get("parent_document_id"),
            "is_current_version": restored.get("is_current_version"),
            "related_application_id": str(restored["related_application_id"]) if restored.get("related_application_id") else None,
            "approved_by_leasing_company": restored.get("approved_by_leasing_company"),
            "leasing_company_status": restored.get("leasing_company_status"),
            "leasing_company_comments": restored.get("leasing_company_comments"),
            "leasing_company_reviewed_at": _isoformat(restored.get("leasing_company_reviewed_at")),
            "extracted_data": restored.get("extracted_data"),
            "recognition_status": restored.get("recognition_status"),
            "recognition_error": restored.get("recognition_error"),
            "dbrain_task_id": restored.get("dbrain_task_id"),
            "recognized_at": _isoformat(restored.get("recognized_at")),
            "uploaded_at": _isoformat(restored.get("uploaded_at")),
            "verified_at": _isoformat(restored.get("verified_at")),
            "verified_by": restored.get("verified_by"),
            "created_at": _isoformat(restored.get("created_at")),
            "updated_at": _isoformat(restored.get("updated_at")),
            "_deleted": False,
        })
    return {
        "message": "Документ восстановлен",
        "document": restored,
    }
