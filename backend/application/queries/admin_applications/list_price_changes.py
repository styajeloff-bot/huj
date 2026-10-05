"""Admin read model for requested-price audit history."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from domain.errors import ApplicationNotFoundError
from infrastructure.repositories import application_repository as repo


@dataclass(frozen=True, slots=True)
class ListApplicationPriceChangesQuery:
    application_id: UUID
    limit: int = 50
    offset: int = 0


async def handle_list_application_price_changes(
    query: ListApplicationPriceChangesQuery,
    session: AsyncSession,
) -> dict[str, Any]:
    if await repo.get_by_id(session, query.application_id) is None:
        raise ApplicationNotFoundError(query.application_id)
    items, total = await repo.list_special_equipment_price_changes(
        session,
        application_id=query.application_id,
        limit=query.limit,
        offset=query.offset,
    )
    return {
        "items": items,
        "total": total,
        "limit": query.limit,
        "offset": query.offset,
    }


__all__ = [
    "ListApplicationPriceChangesQuery",
    "handle_list_application_price_changes",
]
