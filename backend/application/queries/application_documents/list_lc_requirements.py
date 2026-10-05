"""List leasing_company_document_requirements for an LC.

Authorization: the LC itself or a ``carcraft_employee``. Other roles are
rejected — clients / dealers use the application-scoped
``/documents/requirements/{application_id}`` endpoint (D1) which resolves
requirements across the application's selected LCs.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from domain.entities.leasing_company_document_requirement import (
    ensure_can_read_for_lc,
)
from domain.errors import LeasingCompanyNotFoundError
from infrastructure.repositories import (
    application_documents_repository as ad_repo,
)
from infrastructure.repositories import (
    leasing_company_document_requirements_repository as lcdr_repo,
)


@dataclass
class ListLcRequirementsQuery:
    leasing_company_id: UUID
    actor_user_id: UUID
    actor_role: str
    actor_leasing_company_id: UUID | None = None


async def handle_list_lc_requirements(
    query: ListLcRequirementsQuery,
    session: AsyncSession,
) -> dict[str, Any]:
    ensure_can_read_for_lc(
        actor_role=query.actor_role,
        actor_leasing_company_id=query.actor_leasing_company_id,
        target_leasing_company_id=query.leasing_company_id,
    )

    if not await ad_repo.leasing_company_exists(
        session, query.leasing_company_id
    ):
        raise LeasingCompanyNotFoundError(query.leasing_company_id)

    rows = await lcdr_repo.list_for_lc_with_types(
        session, query.leasing_company_id
    )
    name = await lcdr_repo.get_leasing_company_name(
        session, query.leasing_company_id
    )
    summary = {
        "total": len(rows),
        "required": sum(1 for r in rows if r.get("is_required")),
        "mandatory": sum(1 for r in rows if r.get("is_mandatory")),
        "auto_approve": sum(1 for r in rows if r.get("auto_approve")),
    }
    return {
        "leasing_company": {
            "id": query.leasing_company_id,
            "name": name,
        },
        "requirements": rows,
        "summary": summary,
    }
