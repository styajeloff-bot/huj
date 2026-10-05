"""List exchange requests relevant to a dealer."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.queries.exchange.list_lc_requests import enrich_requests
from application.services.exchange_access import require_exchange_company
from infrastructure.repositories import exchange_request_repository as repo


@dataclass
class ListDealerRequestsQuery:
    dealer_id: UUID
    company_id: UUID | None = None
    status: str | None = None
    page: int = 1
    limit: int = 20


async def handle_list_dealer_requests(
    query: ListDealerRequestsQuery, session: AsyncSession
) -> dict[str, Any]:
    company = await require_exchange_company(session, user_id=query.dealer_id,
        role="dealer", company_id=query.company_id)
    page = max(1, query.page)
    limit = max(1, query.limit)
    offset = (page - 1) * limit

    rows = await repo.list_for_dealer(
        session,
        dealer_id=query.dealer_id,
        company_id=company,
        status=query.status,
        limit=limit,
        offset=offset,
    )
    total = await repo.count_for_dealer(
        session,
        dealer_id=query.dealer_id,
        company_id=company,
        status=query.status,
    )
    pages = (total + limit - 1) // limit if total else 0

    enriched = await enrich_requests(
        session, rows, own_dealer_id=query.dealer_id
    )
    from application.queries.exchange.get_dealer_request import anonymize_competing_bid
    for request in enriched:
        request["warehouses"] = [w for w in request.get("warehouses", []) if w.get("dealer_id") == company]
        request["dealer_comments"] = [c for c in request.get("dealer_comments", []) if c.get("dealer_id") == company]
        request["bids"] = [bid if bid.get("is_own") else anonymize_competing_bid(bid) for bid in request.get("bids", [])]

    return {
        "requests": enriched,
        "pagination": {
            "page": page,
            "limit": limit,
            "total": total,
            "pages": pages,
        },
    }
