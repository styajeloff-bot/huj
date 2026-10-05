"""List leasing companies (admin, full directory) query."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.repositories import admin_companies_repository as repo


@dataclass
class ListLeasingCompaniesAllQuery:
    """Empty marker — listing is unfiltered."""


async def handle_list_leasing_companies_all(
    _query: ListLeasingCompaniesAllQuery,
    session: AsyncSession,
) -> dict[str, Any]:
    companies = await repo.list_leasing_companies_all(session)
    return {"companies": companies}
