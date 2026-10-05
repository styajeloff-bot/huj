"""Enhanced listing of the current user's documents.

Returns the same rows as :func:`handle_list_documents` plus:
- the aggregated list of document-type requirements resolved from every
  leasing-company the user's applications have selected;
- a per-type ``has_document`` hint so the UI can render ✓/✗ next to
  each requirement without an extra round-trip.

The matching is done on ``document_type`` (string) since that is what
both the ``documents`` rows and the ``leasing_company_document_requirements``
reference.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.repositories import documents_repository as docs_repo


@dataclass
class ListUserDocumentsEnhancedQuery:
    actor_user_id: UUID
    actor_role: str
    actor_company_id: UUID | None


async def handle_list_user_documents_enhanced(
    query: ListUserDocumentsEnhancedQuery,
    session: AsyncSession,
) -> dict:
    if query.actor_company_id is None:
        return {
            "documents": [],
            "requirements": [],
            "total": 0,
        }
    documents = await docs_repo.list_for_company(
        session,
        company_id=query.actor_company_id,
        only_current=True,
    )
    uploaded_types = {doc["document_type"] for doc in documents}

    lc_ids = await docs_repo.collect_lc_ids_for_company(
        session, company_id=query.actor_company_id
    )
    raw_requirements = await docs_repo.list_requirements_for_lcs(
        session, lc_ids
    )
    enriched: list[dict[str, Any]] = []
    for req in raw_requirements:
        doc_type = req["document_type"]
        enriched.append(
            {
                **req,
                "has_document": doc_type in uploaded_types,
            }
        )
    return {
        "documents": documents,
        "requirements": enriched,
        "total": len(documents),
    }
