"""Build the PDF export payload for a single leasing application."""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.permissions import ensure_application_full_data_access
from application.queries.applications.get_application import (
    GetApplicationQuery,
    handle_get_application,
)
from infrastructure.repositories import documents_repository as documents_repo
from infrastructure.services.application_export_pdf import (
    ApplicationExportInput,
    render_application_export_pdf,
)


@dataclass
class ExportApplicationQuery:
    application_id: uuid.UUID
    actor_id: UUID
    actor_role: str
    actor_company_id: UUID | None
    actor_leasing_company_id: UUID | None = None


async def handle_export_application_pdf(
    query: ExportApplicationQuery, session: AsyncSession
) -> bytes:
    detail = await handle_get_application(
        GetApplicationQuery(
            application_id=query.application_id,
            actor_id=query.actor_id,
            actor_role=query.actor_role,
            actor_company_id=query.actor_company_id,
            actor_leasing_company_id=query.actor_leasing_company_id,
        ),
        session,
    )
    await ensure_application_full_data_access(
        session, application_id=query.application_id, actor_role=query.actor_role,
        actor_company_id=query.actor_company_id,
    )
    documents = await documents_repo.list_for_application(
        session, application_id=query.application_id
    )
    payload = ApplicationExportInput(
        application=detail,
        company=detail.get("company"),
        owner=detail.get("owner"),
        questionnaire=detail.get("questionnaire"),
        vehicles=detail.get("vehicles") or [],
        vehicle_calculations=detail.get("vehicle_calculations") or [],
        documents=documents,
        selected_companies_info=detail.get("selected_companies_info") or [],
    )
    return render_application_export_pdf(payload)
