"""List bids visible to the current dealer (their own) or LC (for requests)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.services.exchange_access import (
    require_exchange_bid_access,
    require_exchange_company,
)
from domain.errors import ExchangeRequestAccessDeniedError
from infrastructure.repositories import exchange_bid_repository as repo


@dataclass
class ListBidsQuery:
    dealer_id: UUID
    company_id: UUID | None = None


async def handle_list_bids(
    query: ListBidsQuery, session: AsyncSession
) -> dict[str, Any]:
    company = await require_exchange_company(session, user_id=query.dealer_id,
        role="dealer", company_id=query.company_id)
    bids = await repo.list_for_dealer(session, dealer_id=query.dealer_id)
    visible = []
    for bid in bids:
        try:
            await require_exchange_bid_access(session, bid, user_id=query.dealer_id,
                role="dealer", company_id=company)
        except ExchangeRequestAccessDeniedError:
            continue
        visible.append(bid)
    return {"bids": visible}
