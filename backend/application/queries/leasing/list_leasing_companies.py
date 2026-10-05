"""List active leasing companies — public directory used by dealer UI."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.repositories import (
    leasing_company_application_repository as lca_repo,
)


@dataclass
class ListLeasingCompaniesQuery:
    pass


async def handle_list_leasing_companies(
    _query: ListLeasingCompaniesQuery, session: AsyncSession
) -> dict[str, Any]:
    companies = await lca_repo.list_active_leasing_companies(session)
    return {"companies": companies, "total": len(companies)}
