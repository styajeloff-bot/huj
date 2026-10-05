"""Leasing-company document-requirements repository — Phase 4 D2.

Owns ``leasing_company_document_requirements`` (ORM class
:class:`LeasingCompanyDocumentRequirement` in ``applications.py``).
Reference reads against ``document_types``.

Returns dicts only.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

from sqlalchemy import and_, delete, select
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.models.applications import (
    LeasingCompanyDocumentRequirement,
)
from infrastructure.models.companies import Company, LeasingCompany
from infrastructure.models.documents import DocumentType
from infrastructure.repository_timing import timed_repository


def _rowcount(result: object) -> int:
    return int(cast("CursorResult[Any]", result).rowcount or 0)


def _req_to_dict(row: LeasingCompanyDocumentRequirement) -> dict[str, Any]:
    return {
        "id": row.id,
        "leasing_company_id": row.leasing_company_id,
        "document_type_id": row.document_type_id,
        "is_required": bool(row.is_required),
        "is_mandatory": bool(row.is_mandatory),
        "sort_order": row.sort_order if row.sort_order is not None else 0,
        "is_active": bool(row.is_active),
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }

# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------

@timed_repository
async def list_for_lc_with_types(
    session: AsyncSession, leasing_company_id: UUID
) -> list[dict[str, Any]]:
    """Return requirements joined with ``document_types`` metadata."""
    stmt = (
        select(
            LeasingCompanyDocumentRequirement.id,
            LeasingCompanyDocumentRequirement.leasing_company_id,
            LeasingCompanyDocumentRequirement.document_type_id,
            LeasingCompanyDocumentRequirement.is_required,
            LeasingCompanyDocumentRequirement.is_mandatory,
            LeasingCompanyDocumentRequirement.sort_order,
            LeasingCompanyDocumentRequirement.is_active,
            DocumentType.type_code,
            DocumentType.display_name,
            DocumentType.description,
            DocumentType.file_types,
            DocumentType.max_file_size_mb,
            DocumentType.auto_approve,
            DocumentType.validation_rules,
        )
        .join(
            DocumentType,
            DocumentType.id
            == LeasingCompanyDocumentRequirement.document_type_id,
        )
        .where(
            LeasingCompanyDocumentRequirement.leasing_company_id
            == leasing_company_id,
            LeasingCompanyDocumentRequirement.is_active.is_(True),
        )
        .order_by(
            LeasingCompanyDocumentRequirement.sort_order.asc().nullslast(),
            DocumentType.display_name.asc().nullslast(),
        )
    )
    result = await session.execute(stmt)
    return [
        {
            "id": row.id,
            "leasing_company_id": row.leasing_company_id,
            "document_type_id": row.document_type_id,
            "document_type": row.type_code,
            "display_name": row.display_name,
            "description": row.description,
            "file_types": list(row.file_types) if row.file_types else [],
            "max_file_size_mb": row.max_file_size_mb,
            "auto_approve": bool(row.auto_approve),
            "validation_rules": row.validation_rules,
            "is_required": bool(row.is_required),
            "is_mandatory": bool(row.is_mandatory),
            "sort_order": row.sort_order if row.sort_order is not None else 0,
            "is_active": bool(row.is_active),
        }
        for row in result.all()
    ]

@timed_repository
async def get_document_type_id(
    session: AsyncSession, type_code: str
) -> UUID | None:
    stmt = select(DocumentType.id).where(DocumentType.type_code == type_code)
    row = (await session.execute(stmt)).first()
    return row[0] if row is not None else None

@timed_repository
async def get_leasing_company_name(
    session: AsyncSession, leasing_company_id: UUID
) -> str | None:
    stmt = (
        select(Company.name)
        .join(LeasingCompany, LeasingCompany.company_id == Company.id)
        .where(LeasingCompany.id == leasing_company_id)
    )
    row = (await session.execute(stmt)).first()
    return str(row[0]) if row is not None and row[0] else None

# ---------------------------------------------------------------------------
# Writes
# ---------------------------------------------------------------------------

@timed_repository
async def delete_requirements_for_lc(
    session: AsyncSession, leasing_company_id: UUID
) -> int:
    """Hard-delete all requirements for ``leasing_company_id``.

    Returns the number of rows deleted. Used by the "replace wholesale"
    update flow that mirrors Express.
    """
    stmt = delete(LeasingCompanyDocumentRequirement).where(
        LeasingCompanyDocumentRequirement.leasing_company_id
        == leasing_company_id
    )
    result = await session.execute(stmt)
    return _rowcount(result)

@timed_repository
async def insert_requirement(
    session: AsyncSession,
    *,
    leasing_company_id: UUID,
    document_type_id: UUID,
    is_required: bool,
    is_mandatory: bool,
    sort_order: int,
) -> UUID:
    now = datetime.now(UTC)
    row = LeasingCompanyDocumentRequirement(
        leasing_company_id=leasing_company_id,
        document_type_id=document_type_id,
        is_required=is_required,
        is_mandatory=is_mandatory,
        sort_order=sort_order,
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    session.add(row)
    await session.flush()
    return row.id

@timed_repository
async def find_existing(
    session: AsyncSession,
    *,
    leasing_company_id: UUID,
    document_type_id: UUID,
) -> dict[str, Any] | None:
    stmt = select(LeasingCompanyDocumentRequirement).where(
        and_(
            LeasingCompanyDocumentRequirement.leasing_company_id
            == leasing_company_id,
            LeasingCompanyDocumentRequirement.document_type_id
            == document_type_id,
        )
    )
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        return None
    return _req_to_dict(row)

__all__ = [
    "delete_requirements_for_lc",
    "find_existing",
    "get_document_type_id",
    "get_leasing_company_name",
    "insert_requirement",
    "list_for_lc_with_types",
]
