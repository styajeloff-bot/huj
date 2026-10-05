"""Resolve document-type requirements for a given application.

Joins the application's ``selected_leasing_companies`` against
``leasing_company_document_requirements`` and decorates each entry with
the matching ``documents`` row uploaded by the company (if any).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any
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
class ListDocumentRequirementsQuery:
    application_id: uuid.UUID
    actor_user_id: UUID
    actor_role: str
    actor_company_id: UUID | None
    actor_leasing_company_id: UUID | None = None


async def handle_list_document_requirements(
    query: ListDocumentRequirementsQuery,
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

    selected = application.get("selected_leasing_companies") or []
    raw_requirements = await docs_repo.list_requirements_for_lcs(
        session, list(selected)
    )
    type_codes = [r["document_type"] for r in raw_requirements]
    existing_map = await docs_repo.find_existing_for_company_by_type(
        session,
        company_id=application["company_id"],
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
                    existing.get("leasing_company_status") if existing else None
                ),
            }
        )
    return {
        "application_id": query.application_id,
        "requirements": out,
        "total": len(out),
    }
