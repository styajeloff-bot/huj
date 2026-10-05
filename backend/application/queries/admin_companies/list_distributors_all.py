"""List distributors (admin, full directory) query."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.repositories import admin_companies_repository as repo


@dataclass
class ListDistributorsAllQuery:
    """Empty marker — listing is unfiltered (all active distributors)."""


async def handle_list_distributors_all(
    _query: ListDistributorsAllQuery,
    session: AsyncSession,
) -> dict[str, Any]:
    distributors = await repo.list_distributors_all(session)
    return {"distributors": distributors}
