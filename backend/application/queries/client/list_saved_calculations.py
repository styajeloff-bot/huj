"""Query: list the user's saved calculations newest-first."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.repositories import client_repository as repo


@dataclass(frozen=True)
class ListSavedCalculationsQuery:
    user_id: UUID


async def handle_list_saved_calculations(
    query: ListSavedCalculationsQuery, session: AsyncSession
) -> list[dict[str, Any]]:
    return cast(
        "list[dict[str, Any]]",
        await repo.list_saved_calculations(session, query.user_id),
    )
