"""Get a single bid with access-gated visibility."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.services.exchange_access import require_exchange_bid_access
from domain.errors import (
    ExchangeBidAccessDeniedError,
    ExchangeBidNotFoundError,
)
from infrastructure.repositories import (
    exchange_bid_repository as bid_repo,
)


@dataclass
class GetBidQuery:
    bid_id: UUID
    user_id: UUID
    user_role: str
    company_id: UUID | None = None


async def handle_get_bid(
    query: GetBidQuery, session: AsyncSession
) -> dict[str, Any]:
    raw = await bid_repo.get_by_id(session, query.bid_id)
    if raw is None:
        raise ExchangeBidNotFoundError(query.bid_id)

    if query.user_role in {"dealer", "leasing_company", "distributor"}:
        await require_exchange_bid_access(session, raw, user_id=query.user_id,
            role=query.user_role, company_id=query.company_id)
    elif query.user_role != "carcraft_employee":
        raise ExchangeBidAccessDeniedError()

    options = await bid_repo.list_options(session, query.bid_id)
    comments = await bid_repo.list_comments(session, query.bid_id)
    return {
        "bid": raw,
        "options": options,
        "comments": comments,
    }
