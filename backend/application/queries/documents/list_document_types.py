"""List every configured :class:`DocumentType` (reference data).

Used by the front-end document upload form to render the type-selector;
returns the full config needed to validate uploads client-side
(file_types, max_file_size_mb, validation_rules).
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.repositories import document_types_repository as types_repo


@dataclass
class ListDocumentTypesQuery:
    """No filters — the full list is always returned."""


async def handle_list_document_types(
    query: ListDocumentTypesQuery,
    session: AsyncSession,
) -> dict:
    _ = query
    types = await types_repo.list_all(session)
    return {"types": types, "total": len(types)}
