"""List documents visible to the current user (own company scope)."""
from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.repositories import documents_repository as docs_repo


@dataclass
class ListDocumentsQuery:
    actor_user_id: UUID
    actor_role: str
    actor_company_id: UUID | None
    only_current: bool = True


async def handle_list_documents(
    query: ListDocumentsQuery,
    session: AsyncSession,
) -> dict:
    if query.actor_company_id is None:
        return {"documents": [], "total": 0}
    documents = await docs_repo.list_for_company(
        session,
        company_id=query.actor_company_id,
        only_current=query.only_current,
    )
    return {"documents": documents, "total": len(documents)}
