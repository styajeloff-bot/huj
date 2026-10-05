"""Queries for positions catalog."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.repositories import positions_repository


@dataclass(frozen=True, slots=True)
class ListPositionsQuery:
    only_active: bool = False


async def handle_list_positions(
    query: ListPositionsQuery,
    session: AsyncSession,
) -> dict[str, Any]:
    """Handle listing positions."""
    items = await positions_repository.list_positions(
        session,
        only_active=query.only_active,
    )
    return {"items": items}
