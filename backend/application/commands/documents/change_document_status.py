
"""Change a document's review status (admin / employee path).

Validates the transition through the ``Document`` aggregate, persists the
new status on the row and writes a row to ``document_status_history`` for
the audit trail. The matching event is published by the caller (router)
when commit succeeds — D3 may also append history rows on its own.
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
class ChangeDocumentStatusCommand:
    document_id: UUID
    actor_user_id: UUID
    actor_role: str
    new_status: str
    comments: str | None = None


async def handle_change_document_status(
    cmd: ChangeDocumentStatusCommand,
    session: AsyncSession,
) -> dict:
    current = await docs_repo.get_by_id(session, cmd.document_id)
    if current is None:
        raise DocumentNotFoundError(cmd.document_id)
    entity = Document.from_dict(current)
    entity.ensure_can_change_status(cmd.new_status)

    await docs_repo.update_review_status(
        session,
        cmd.document_id,
        new_status=cmd.new_status,
        comments=cmd.comments,
        reviewer_user_id=cmd.actor_user_id,
    )
    await hist_repo.append_document_status_history(
        document_id=cmd.document_id,
        old_status=entity.review_status,
        new_status=cmd.new_status,
        changed_by=cmd.actor_user_id,
        comments=cmd.comments,
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
        "message": "Статус документа обновлён",
        "document": updated,
    }
