"""List every version (root + children) of a document chain."""
from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.queries.documents.get_document import (
    GetDocumentQuery,
    handle_get_document,
)
from infrastructure.repositories import documents_repository as docs_repo


@dataclass
class ListDocumentVersionsQuery:
    document_id: UUID
    actor_user_id: UUID
    actor_role: str
    actor_company_id: UUID | None
    actor_leasing_company_id: UUID | None = None


async def handle_list_document_versions(
    query: ListDocumentVersionsQuery,
    session: AsyncSession,
) -> dict:
    # First resolve access via the underlying document — this raises
    # DocumentNotFoundError / DocumentAccessDeniedError as appropriate.
    await handle_get_document(
        GetDocumentQuery(
            document_id=query.document_id,
            actor_user_id=query.actor_user_id,
            actor_role=query.actor_role,
            actor_company_id=query.actor_company_id,
            actor_leasing_company_id=query.actor_leasing_company_id,
        ),
        session,
    )
    versions = await docs_repo.list_versions(session, query.document_id)
    return {"versions": versions, "total": len(versions)}
