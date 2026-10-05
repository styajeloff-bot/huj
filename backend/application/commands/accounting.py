"""Accounting-report commands (write-side).

`RefreshAccountingCommand` forces a provider round-trip, bypassing the
TTL cache. Used by the frontend "Обновить" button when a user wants the
latest snapshot right now.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from application.queries.accounting import (
    GetAccountingReportQuery,
    handle_get_accounting_report,
)
from domain.services.accounting_provider import AccountingProvider


@dataclass
class RefreshAccountingCommand:
    inn: str


async def handle_refresh_accounting(
    command: RefreshAccountingCommand,
    session: AsyncSession,
    provider: AccountingProvider,
) -> dict[str, Any]:
    return await handle_get_accounting_report(
        GetAccountingReportQuery(inn=command.inn, force_refresh=True),
        session,
        provider,
    )
