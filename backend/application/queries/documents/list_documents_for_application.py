"""List all documents attached to a given leasing application."""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.permissions import require_distributor_application_read
from application.services.leasing_access import require_lc_application_access
from domain.errors import (
    ApplicationNotFoundError,
    DocumentAccessDeniedError,
)
from infrastructure.repositories import documents_repository as docs_repo


@dataclass
class ListDocumentsForApplicationQuery:
    application_id: uuid.UUID
    actor_user_id: UUID
    actor_role: str
    actor_company_id: UUID | None
    actor_leasing_company_id: UUID | None = None


async def handle_list_documents_for_application(
    query: ListDocumentsForApplicationQuery,
    session: AsyncSession,
) -> dict:
    await require_distributor_application_read(
        session, user_id=query.actor_user_id, actor_role=query.actor_role,
        actor_company_id=query.actor_company_id,
    )
    application = await docs_repo.get_application(
        session, query.application_id
    )
    if application is None:
        raise ApplicationNotFoundError(query.application_id)

    if query.actor_role != "carcraft_employee":
        if query.actor_role == "leasing_company":
            await require_lc_application_access(
                session, application_id=query.application_id,
                user_id=query.actor_user_id, company_id=query.actor_company_id,
                leasing_company_id=query.actor_leasing_company_id,
            )
        elif (
            query.actor_company_id is None
            or application["company_id"] != query.actor_company_id
        ):
            raise DocumentAccessDeniedError()

    documents = await docs_repo.list_for_application(
        session, application_id=query.application_id
    )
    return {
        "application_id": query.application_id,
        "documents": documents,
        "total": len(documents),
    }
