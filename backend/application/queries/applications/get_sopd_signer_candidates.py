"""Resolve SOPD signer candidates for an authorized application."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from application.queries.applications.get_application import (
    ApplicationAccessQuery,
    get_authorized_application,
)
from application.services.application_sopd_candidates import (
    application_signer_candidates,
)
from domain.services.company_lookup import CompanyLookupProvider
from infrastructure.repositories import company_repository as company_repo


@dataclass
class GetSopdSignerCandidatesQuery(ApplicationAccessQuery):
    company_lookup_provider: CompanyLookupProvider | None = None


async def handle_get_sopd_signer_candidates(
    query: GetSopdSignerCandidatesQuery,
    session: AsyncSession,
) -> dict[str, list[dict[str, Any]]]:
    application, _ = await get_authorized_application(query, session)
    company_id = application.get("company_id")
    if company_id is None:
        return {"candidates": []}

    company = await company_repo.get_company_by_id(session, company_id)
    if company is None:
        return {"candidates": []}

    candidates = await application_signer_candidates(
        session, application_id=query.application_id, company=company, provider=query.company_lookup_provider
    )
    return {"candidates": candidates}
