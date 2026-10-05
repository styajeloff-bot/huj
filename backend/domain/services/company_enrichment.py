"""Abstract scheduler for refreshing external company data."""
from __future__ import annotations

from typing import Protocol


class CompanyEnrichmentScheduler(Protocol):
    async def schedule_refresh(self, inn: str) -> None:
        """Schedule background refresh of external company data by INN."""
