"""In-memory fake CompanyLookupProvider for tests."""
from __future__ import annotations

from typing import Any

from domain.errors import CompanyLookupUnavailableError
from domain.values import CompanyInfo


class FakeCompanyLookupProvider:
    def __init__(
        self,
        items: list[CompanyInfo] | None = None,
        enrich_by_inn: dict[str, dict[str, Any] | Exception | None] | None = None,
    ) -> None:
        self.items: list[CompanyInfo] = items or []
        self.enrichment: dict[str, dict[str, Any] | Exception | None] = enrich_by_inn or {}
        self.raise_unavailable: bool = False
        self.calls: list[tuple[str, int]] = []
        self.enrich_calls: list[str] = []

    async def search(self, query: str, limit: int) -> list[CompanyInfo]:
        self.calls.append((query, limit))
        if self.raise_unavailable:
            raise CompanyLookupUnavailableError()
        return self.items[:limit]

    async def enrich_by_inn(self, inn: str) -> dict[str, Any] | None:
        self.enrich_calls.append(inn)
        if self.raise_unavailable:
            raise CompanyLookupUnavailableError()
        result = self.enrichment.get(inn)
        if isinstance(result, Exception):
            raise result
        return result
