"""Synchronous company enrichment from DaData."""
from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from domain.errors import CompanyLookupUnavailableError
from infrastructure.repositories import company_registration_repository as company_repo
from infrastructure.services.company_lookup import get_company_lookup_provider

logger = logging.getLogger("carcraft-backend")


async def enrich_companies_from_dadata(session: AsyncSession, inns: list[str]) -> None:
    """Synchronously enrich companies from DaData; failures are logged, not raised."""
    if not inns:
        return
    provider = get_company_lookup_provider()
    for inn in inns:
        try:
            data = await provider.enrich_by_inn(inn)
            if data:
                await company_repo.save_dadata_enrichment(session, inn, data)
            else:
                await company_repo.create_or_update_pending_enrichment(session, inn)
        except CompanyLookupUnavailableError:
            logger.warning("DaData enrichment unavailable for INN %s", inn)
            await company_repo.create_or_update_pending_enrichment(session, inn)
        except Exception:
            logger.exception("DaData enrichment failed for INN %s", inn)
            await company_repo.create_or_update_pending_enrichment(session, inn)
