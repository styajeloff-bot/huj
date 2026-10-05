"""Document types repository — read-only access to ``document_types``.

The table is effectively reference data (populated by seed migrations),
so the repo exposes only lookups. Returns plain dicts.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.models.documents import DocumentType
from infrastructure.repository_timing import timed_repository


def _to_dict(row: DocumentType) -> dict[str, Any]:
    return {
        "id": row.id,
        "name": row.name,
        "type_code": row.type_code,
        "display_name": row.display_name,
        "description": row.description,
        "is_required_for_all": row.is_required_for_all,
        "file_types": list(row.file_types) if row.file_types else [],
        "max_file_size_mb": row.max_file_size_mb,
        "validation_rules": row.validation_rules,
        "auto_approve": row.auto_approve,
        "has_form": row.has_form,
        "form_schema": row.form_schema,
    }

@timed_repository
async def list_all(session: AsyncSession) -> list[dict[str, Any]]:
    stmt = select(DocumentType).order_by(DocumentType.id)
    rows = (await session.execute(stmt)).scalars().all()
    return [_to_dict(r) for r in rows]

@timed_repository
async def get_by_type_code(
    session: AsyncSession, type_code: str
) -> dict[str, Any] | None:
    stmt = select(DocumentType).where(DocumentType.type_code == type_code)
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        return None
    return _to_dict(row)

@timed_repository
async def get_many_by_type_codes(
    session: AsyncSession, type_codes: list[str]
) -> list[dict[str, Any]]:
    if not type_codes:
        return []
    stmt = select(DocumentType).where(DocumentType.type_code.in_(type_codes))
    rows = (await session.execute(stmt)).scalars().all()
    return [_to_dict(r) for r in rows]

__all__ = [
    "get_by_type_code",
    "get_many_by_type_codes",
    "list_all",
]
