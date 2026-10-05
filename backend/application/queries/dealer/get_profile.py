"""Query: full dealer profile — joined user + company + sales stats."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from domain.errors import UserNotFoundError
from infrastructure.repositories import dealer_repository as repo


@dataclass(frozen=True)
class GetDealerProfileQuery:
    user_id: UUID


async def handle_get_dealer_profile(
    query: GetDealerProfileQuery, session: AsyncSession
) -> dict[str, Any]:
    profile = await repo.get_dealer_user(session, query.user_id)
    if profile is None:
        raise UserNotFoundError()
    stats = await repo.dealer_sales_stats(session, profile["user"]["company_id"])
    return {
        "profile": profile["user"],
        "company": profile["company"],
        "stats": stats,
    }
