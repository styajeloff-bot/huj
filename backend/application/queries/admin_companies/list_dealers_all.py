"""List dealers (admin, full directory) query."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.repositories import admin_users_repository as repo


@dataclass
class ListDealersAllQuery:
    """Empty marker — admin listing is unfiltered (all active dealers)."""


async def handle_list_dealers_all(
    _query: ListDealersAllQuery,
    session: AsyncSession,
) -> dict[str, Any]:
    dealers = await repo.list_active_dealers(session)
    return {"dealers": dealers}
