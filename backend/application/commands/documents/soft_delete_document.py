
"""Soft-delete a document.

The ``documents`` ORM model has no dedicated ``is_deleted`` column — we
reuse ``is_current_version=False`` as the hide marker. Only the owner
or a carcraft employee may trigger a soft-delete.
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
class SoftDeleteDocumentCommand:
    document_id: UUID
    actor_user_id: UUID
    actor_role: str
    actor_company_id: UUID | None


async def handle_soft_delete_document(
    cmd: SoftDeleteDocumentCommand,
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
    await docs_repo.soft_delete(session, cmd.document_id)
    await hist_repo.append_document_status_history(
        document_id=cmd.document_id,
        old_status=entity.review_status,
        new_status="deleted",
        changed_by=cmd.actor_user_id,
        comments="soft-delete",
    )
    updated = await docs_repo.get_by_id(session, cmd.document_id)
    if updated is not None:
        emit_document_changed({
            "document_id": updated["id"],
            "company_id": updated["company_id"],
            "document_type": updated.get("document_type"),
            "file_path": updated.get("file_path"),
            "file_name": updated.get("file_name"),
            "file_size": updated.get("file_size"),
            "s3_key": updated.get("s3_key"),
            "period_label": updated.get("period_label"),
            "comments": updated.get("comments"),
            "is_required": updated.get("is_required"),
            "status": updated.get("status"),
            "version": updated.get("version"),
            "parent_document_id": updated.get("parent_document_id"),
            "is_current_version": updated.get("is_current_version"),
            "related_application_id": str(updated["related_application_id"]) if updated.get("related_application_id") else None,
            "approved_by_leasing_company": updated.get("approved_by_leasing_company"),
            "leasing_company_status": updated.get("leasing_company_status"),
            "leasing_company_comments": updated.get("leasing_company_comments"),
            "leasing_company_reviewed_at": _isoformat(updated.get("leasing_company_reviewed_at")),
            "extracted_data": updated.get("extracted_data"),
            "recognition_status": updated.get("recognition_status"),
            "recognition_error": updated.get("recognition_error"),
            "dbrain_task_id": updated.get("dbrain_task_id"),
            "recognized_at": _isoformat(updated.get("recognized_at")),
            "uploaded_at": _isoformat(updated.get("uploaded_at")),
            "verified_at": _isoformat(updated.get("verified_at")),
            "verified_by": updated.get("verified_by"),
            "created_at": _isoformat(updated.get("created_at")),
            "updated_at": _isoformat(updated.get("updated_at")),
            "_deleted": False,
        })
    return {
        "message": "Документ помечен как удалённый",
        "document_id": cmd.document_id,
    }
