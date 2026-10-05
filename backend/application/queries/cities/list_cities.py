"""List cities (admin)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.repositories import city_repository as repo


@dataclass
class ListCitiesQuery:
    pass


async def handle_list_cities(
    _query: ListCitiesQuery, session: AsyncSession
) -> dict[str, Any]:
    items = await repo.list_cities(session)
    return {"cities": items}
