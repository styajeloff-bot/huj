"""Abstract port for external company-info lookup providers."""
from __future__ import annotations

from typing import Any, Protocol

from domain.values import CompanyInfo


class CompanyLookupProvider(Protocol):
    """Provider-agnostic contract for looking up company info by name or INN.

    Concrete implementations live in `infrastructure/services/company_lookup/`.
    The domain must NOT know which provider is used (implementation detail).
    """

    async def search(self, query: str, limit: int) -> list[CompanyInfo]:
        """Return up to `limit` normalized CompanyInfo entries matching `query`.

        Empty result is a successful-but-empty list, never an exception.
        Raises `CompanyLookupUnavailableError` on provider/network failure.
        """
        ...

    async def enrich_by_inn(self, inn: str) -> dict[str, Any] | None:
        """Fetch full enrichment data by INN.

        Returns the raw provider-specific data block, or ``None`` if not found.
        Raises ``CompanyLookupUnavailableError`` on provider/network failure.
        """
        ...
