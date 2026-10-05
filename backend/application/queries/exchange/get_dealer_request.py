"""Return an exchange request for a dealer viewer (anonymized competing bids).

Shape mirrors the listing enrichment: a single ``request`` dict with
vehicle / warehouses / options / bids embedded. Dealer-specific rules:

* ``warehouses`` — filtered to the viewer's own dealer_id or company;
* ``dealer_comments`` — only the viewer's own;
* ``bids`` — the viewer's own bid is kept intact, competing bids are
  anonymized (dealer_id / comment / files stripped).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.queries.exchange.list_lc_requests import enrich_requests
from application.services.exchange_access import can_read_exchange_request
from domain.errors import (
    ExchangeRequestAccessDeniedError,
    ExchangeRequestNotFoundError,
)
from infrastructure.repositories import (
    exchange_request_repository as req_repo,
)


@dataclass
class GetDealerRequestQuery:
    request_id: UUID
    dealer_id: UUID
    company_id: UUID | None = None


def anonymize_competing_bid(bid: dict[str, Any]) -> dict[str, Any]:
    stripped = dict(bid)
    stripped["dealer_id"] = None
    stripped["dealer_company_id"] = None
    stripped["dealer_name"] = None
    stripped["comment"] = None
    stripped["bid_file_url"] = None
    stripped["bid_file_name"] = None
    stripped["kp_file_url"] = None
    stripped["kp_file_name"] = None
    stripped["kp_status"] = None
    stripped["kp_dealer_comment"] = None
    stripped["kp_sent_at"] = None
    stripped["kp_responded_at"] = None
    stripped["is_own"] = False
    return stripped


async def handle_get_dealer_request(
    query: GetDealerRequestQuery, session: AsyncSession
) -> dict[str, Any]:
    raw = await req_repo.get_by_id(session, query.request_id)
    if raw is None:
        raise ExchangeRequestNotFoundError(query.request_id)
    company_ids = await req_repo.list_company_ids_for_request(
        session, query.request_id
    )

    if query.company_id is None or query.company_id not in company_ids or not await can_read_exchange_request(
        session, request_id=query.request_id, user_id=query.dealer_id, role="dealer", company_id=query.company_id,
    ):
        raise ExchangeRequestAccessDeniedError()

    enriched = (
        await enrich_requests(session, [raw], own_dealer_id=query.dealer_id)
    )[0]

    # Dealer view hides competitors' warehouses and company-level comments.
    def _warehouse_visible(w: dict[str, Any]) -> bool:
        return w.get("dealer_id") == query.company_id

    enriched["warehouses"] = [
        w for w in enriched.get("warehouses") or [] if _warehouse_visible(w)
    ]
    enriched["dealer_comments"] = [
        c
        for c in enriched.get("dealer_comments") or []
        if c.get("dealer_id") == query.company_id
    ]
    enriched["bids"] = [
        bid if bid.get("is_own") else anonymize_competing_bid(bid)
        for bid in enriched.get("bids") or []
    ]
    files = await req_repo.list_files(session, query.request_id)
    enriched["files"] = files
    return {
        "request": enriched,
        "warehouses": enriched["warehouses"],
        "options": enriched["options"],
        "dealer_comments": enriched["dealer_comments"],
        "bids": enriched["bids"],
        "files": files,
    }
