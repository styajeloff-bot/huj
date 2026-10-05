"""Read-only distributor Exchange view, using the notification object policy."""
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.queries.exchange.list_lc_requests import enrich_requests
from application.services.exchange_access import (
    can_read_exchange_request,
    require_exchange_company,
)
from domain.errors import ExchangeRequestAccessDeniedError, ExchangeRequestNotFoundError
from infrastructure.repositories import (
    distributor_dealer_repository as distributor_repo,
)
from infrastructure.repositories import exchange_request_repository as repo


async def list_distributor_requests(
    session: AsyncSession, *, user_id: UUID, company_id: UUID | None,
    status: str | None = None, page: int = 1, limit: int = 20,
) -> dict[str, Any]:
    company = await require_exchange_company(session, user_id=user_id, role="distributor", company_id=company_id)
    dealers = await distributor_repo.get_linked_dealer_ids(session, company)
    rows, total, _ = await repo.list_for_distributor(session, company_id=company,
        dealer_company_ids=dealers, status=status, limit=limit, offset=(page - 1) * limit)
    enriched = await enrich_requests(session, rows)
    for request in enriched:
        _project_distributor(request, company, set(dealers))
    return {"items": enriched,
            "pagination": {"page": page, "limit": limit, "total": total,
                           "pages": (total + limit - 1) // limit}}


async def get_distributor_request_counts(
    session: AsyncSession, *, user_id: UUID, company_id: UUID | None,
) -> dict[str, Any]:
    company = await require_exchange_company(session, user_id=user_id, role="distributor", company_id=company_id)
    dealers = await distributor_repo.get_linked_dealer_ids(session, company)
    _, _, counts = await repo.list_for_distributor(session, company_id=company,
        dealer_company_ids=dealers, status=None, limit=1, offset=0)
    return {"counts": counts}


async def get_distributor_request(
    session: AsyncSession, *, request_id: UUID, user_id: UUID, company_id: UUID | None,
) -> dict[str, Any]:
    if not await can_read_exchange_request(session, request_id=request_id,
        user_id=user_id, role="distributor", company_id=company_id):
        raise ExchangeRequestAccessDeniedError()
    raw = await repo.get_by_id(session, request_id)
    if raw is None:
        raise ExchangeRequestNotFoundError(request_id)
    request = (await enrich_requests(session, [raw]))[0]
    request["files"] = await repo.list_files(session, request_id)
    company = await require_exchange_company(session, user_id=user_id, role="distributor", company_id=company_id)
    dealers = set(await distributor_repo.get_linked_dealer_ids(session, company))
    _project_distributor(request, company, dealers)
    return {"request": request, **{key: request[key] for key in (
        "warehouses", "options", "dealer_comments", "bids", "files",
    )}}


def _project_distributor(request: dict[str, Any], company_id: UUID, dealer_ids: set[UUID]) -> None:
    if request.get("distributor_id") == company_id:
        return
    request["warehouses"] = [row for row in request.get("warehouses", []) if row.get("dealer_id") in dealer_ids]
    request["dealer_comments"] = [row for row in request.get("dealer_comments", []) if row.get("dealer_id") in dealer_ids]
    request["bids"] = [row for row in request.get("bids", []) if row.get("dealer_company_id") in dealer_ids]
    request["bid_count"] = len(request["bids"])
    authors = {bid["dealer_id"] for bid in request["bids"]}
    request["files"] = [row for row in request.get("files", []) if row.get("dealer_id") in authors]
