"""Return an LC-owned exchange request with bids and metadata.

Response shape matches the listing enrichment (``enrich_requests``) so the
LC cabinet's detail view and list view read the same keys — ``mark_name``,
``base_price``, ``warehouses``, ``options``, ``bids``, ``bid_count``, etc.
``files`` stays on the top level because it's detail-only and absent from
the list payload.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.queries.exchange.list_lc_requests import enrich_requests
from application.services.exchange_access import require_lc_request_access
from domain.errors import ExchangeRequestNotFoundError
from infrastructure.repositories import (
    exchange_request_repository as req_repo,
)


@dataclass
class GetRequestQuery:
    request_id: UUID
    lc_user_id: UUID
    company_id: UUID | None = field(default=None, kw_only=True)


async def handle_get_request(
    query: GetRequestQuery, session: AsyncSession
) -> dict[str, Any]:
    raw = await req_repo.get_by_id(session, query.request_id)
    if raw is None:
        raise ExchangeRequestNotFoundError(query.request_id)
    await require_lc_request_access(session, raw, user_id=query.lc_user_id, company_id=query.company_id)

    enriched = (await enrich_requests(session, [raw]))[0]
    files = await req_repo.list_files(session, query.request_id)
    enriched["files"] = files
    # Mirror the embedded collections on the top level so the old Express-era
    # callers (``body["warehouses"]``) keep working alongside the new Vue
    # shape (``body.request.warehouses``).
    return {
        "request": enriched,
        "warehouses": enriched["warehouses"],
        "options": enriched["options"],
        "dealer_comments": enriched["dealer_comments"],
        "bids": enriched["bids"],
        "files": files,
    }
