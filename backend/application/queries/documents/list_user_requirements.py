"""Aggregate document requirements across every LC the user has applied to.

Union of requirements from all leasing companies that appear in any of
the user's applications. Each requirement is annotated with the
already-uploaded document (if the user's company owns one of the right
type).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.repositories import documents_repository as docs_repo


@dataclass
class ListUserRequirementsQuery:
    actor_user_id: UUID
    actor_role: str
    actor_company_id: UUID | None
    leasing_company_ids: list[UUID] | None = None


async def handle_list_user_requirements(
    query: ListUserRequirementsQuery,
    session: AsyncSession,
) -> dict:
    """Resolve the set of requirements the user should satisfy.

    If ``leasing_company_ids`` is provided (e.g. from the ``POST``
    variant) the handler uses that list verbatim. Otherwise it falls
    back to the aggregate across every application the user's company
    is part of.
    """
    if query.leasing_company_ids is not None:
        lc_ids = list(query.leasing_company_ids)
    elif query.actor_company_id is None:
        return {"requirements": [], "total": 0}
    else:
        lc_ids = await docs_repo.collect_lc_ids_for_company(
            session, company_id=query.actor_company_id
        )

    raw_requirements = await docs_repo.list_requirements_for_lcs(
        session, lc_ids
    )
    type_codes = [r["document_type"] for r in raw_requirements]
    existing_map: dict[str, dict[str, Any]] = {}
    if query.actor_company_id is not None:
        existing_map = await docs_repo.find_existing_for_company_by_type(
            session,
            company_id=query.actor_company_id,
            document_types=type_codes,
        )
    out: list[dict[str, Any]] = []
    for req in raw_requirements:
        existing = existing_map.get(req["document_type"])
        out.append(
            {
                **req,
                "existing_document_id": existing["id"] if existing else None,
                "existing_status": (
                    existing.get("leasing_company_status")
                    if existing
                    else None
                ),
            }
        )
    return {
        "requirements": out,
        "total": len(out),
    }
