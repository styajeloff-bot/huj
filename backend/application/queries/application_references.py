"""Reference data queries for leasing application forms."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.repositories import application_repository as repo


@dataclass(frozen=True)
class ListLeasingRegionsQuery:
    q: str | None = None


async def handle_list_leasing_purposes(
    session: AsyncSession,
) -> dict[str, list[dict[str, Any]]]:
    return {"purposes": await repo.list_leasing_purposes(session)}


async def handle_list_leasing_regions(
    query: ListLeasingRegionsQuery,
    session: AsyncSession,
) -> dict[str, list[dict[str, Any]]]:
    return {"regions": await repo.list_leasing_regions(session, q=query.q)}
