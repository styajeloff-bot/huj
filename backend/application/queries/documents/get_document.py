"""Fetch a single document by id with ownership / role enforcement."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.permissions import require_distributor_application_read
from application.services.leasing_access import require_lc_application_access
from domain.entities.document import Document
from domain.errors import (
    DocumentAccessDeniedError,
    DocumentNotFoundError,
)
from infrastructure.repositories import documents_repository as docs_repo


@dataclass
class GetDocumentQuery:
    document_id: UUID
    actor_user_id: UUID
    actor_role: str
    actor_company_id: UUID | None
    actor_leasing_company_id: UUID | None = None


async def handle_get_document(
    query: GetDocumentQuery,
    session: AsyncSession,
) -> dict:
    await require_distributor_application_read(
        session, user_id=query.actor_user_id, actor_role=query.actor_role,
        actor_company_id=query.actor_company_id,
    )
    raw = await docs_repo.get_by_id(session, query.document_id)
    if raw is None:
        raise DocumentNotFoundError(query.document_id)
    entity = Document.from_dict(raw)

    if query.actor_role == "carcraft_employee":
        return cast("dict[Any, Any]", raw)
    if query.actor_role == "leasing_company":
        if entity.related_application_id is None:
            raise DocumentAccessDeniedError()
        await require_lc_application_access(
            session, application_id=entity.related_application_id,
            user_id=query.actor_user_id, company_id=query.actor_company_id,
            leasing_company_id=query.actor_leasing_company_id,
        )
        return cast("dict[Any, Any]", raw)
    # client / dealer / distributor — match company_id directly
    if (
        query.actor_company_id is not None
        and entity.company_id == query.actor_company_id
    ):
        return cast("dict[Any, Any]", raw)
    raise DocumentAccessDeniedError()
