"""Approve one submitted document for the authenticated leasing company."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.errors import ServiceError
from application.services.leasing_access import require_lc_application_access
from infrastructure.repositories import (
    application_documents_repository as application_documents_repo,
)


@dataclass(frozen=True)
class ApproveApplicationDocumentCommand:
    application_id: UUID
    document_id: UUID
    actor_user_id: UUID
    actor_company_id: UUID | None
    actor_leasing_company_id: UUID | None


async def handle_approve_application_document(
    cmd: ApproveApplicationDocumentCommand,
    session: AsyncSession,
) -> dict[str, Any]:
    """Approve only the current LC's submitted application-document relation."""
    await require_lc_application_access(
        session,
        application_id=cmd.application_id,
        user_id=cmd.actor_user_id,
        company_id=cmd.actor_company_id,
        leasing_company_id=cmd.actor_leasing_company_id,
    )
    if cmd.actor_leasing_company_id is None:
        # ``require_lc_application_access`` normally rejects this first; retain
        # an explicit guard so the write is never accidentally unscoped.
        raise ServiceError("Лизинговая компания не определена", status_code=400)

    approved, document_request_id = (
        await application_documents_repo.approve_submitted_application_document(
            session,
            application_id=cmd.application_id,
            document_id=cmd.document_id,
            leasing_company_id=cmd.actor_leasing_company_id,
            reviewed_by=cmd.actor_user_id,
        )
    )
    if not approved:
        association = await application_documents_repo.get_application_document(
            session,
            application_id=cmd.application_id,
            document_id=cmd.document_id,
            leasing_company_id=cmd.actor_leasing_company_id,
        )
        if association is None:
            raise ServiceError("Документ не найден", status_code=404)
        raise ServiceError("Документ уже одобрен другим сотрудником.", status_code=409)

    if document_request_id is not None and not await application_documents_repo.mark_request_approved(
        session,
        request_id=document_request_id,
        reviewed_by=cmd.actor_user_id,
    ):
        # The router rolls the transaction back, including the document approval.
        raise ServiceError("Запрос документа уже не актуален", status_code=409)

    return {
        "application_id": cmd.application_id,
        "document_id": cmd.document_id,
        "leasing_company_id": cmd.actor_leasing_company_id,
        "status": "approved",
        "message": "Документ одобрен",
    }
