"""Infrastructure service for background company data enrichment.

Legacy 1C-based scheduler has been retired. Enrichment now happens
synchronously via DaData in the request path (see
``application/commands/company_enrichment.py``). This module is kept as a
no-op adapter so that existing test fixtures that call
``set_company_enrichment_scheduler`` continue to work.
"""
from __future__ import annotations

from domain.services.company_enrichment import CompanyEnrichmentScheduler


class NoopCompanyEnrichmentScheduler:
    """No-op scheduler — background enrichment is no longer used."""

    async def schedule_refresh(self, _inn: str) -> None:
        return None


class _SchedulerState:
    scheduler: CompanyEnrichmentScheduler | None = None


def get_company_enrichment_scheduler() -> CompanyEnrichmentScheduler:
    if _SchedulerState.scheduler is None:
        _SchedulerState.scheduler = NoopCompanyEnrichmentScheduler()
    return _SchedulerState.scheduler


def set_company_enrichment_scheduler(
    scheduler: CompanyEnrichmentScheduler | None,
) -> None:
    _SchedulerState.scheduler = scheduler
