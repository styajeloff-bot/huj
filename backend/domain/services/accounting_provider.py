"""Abstract port for external accounting/financial-report providers."""
from __future__ import annotations

from typing import Protocol

from domain.values_accounting import AccountingReport


class AccountingProvider(Protocol):
    """Provider-agnostic contract for fetching ФНС bookkeeping reports.

    Concrete implementations live in `infrastructure/services/accounting/`.
    The domain must NOT know which provider is used (Parser API, Kontur,
    SPARK, etc.).
    """

    async def fetch_report(self, inn: str) -> AccountingReport | None:
        """Fetch the most recent accounting report for the given ИНН.

        Returns `None` when the source does not publish reports for this
        company (new LLC, IP, not obliged to file). Empty result is NOT
        an exception.

        Raises `AccountingProviderUnavailableError` on provider/network failure.
        """
        ...
