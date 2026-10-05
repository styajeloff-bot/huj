"""Get one dealer group."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.repositories import dealer_group_repository as repo


@dataclass
class GetDealerGroupQuery:
    group_id: UUID


async def handle_get_dealer_group(
    query: GetDealerGroupQuery, session: AsyncSession
) -> dict[str, Any] | None:
    return cast("dict[str, Any] | None", await repo.get_by_id(session, query.group_id))
