"""Exchange access: fresh role/membership, company permissions, object ownership."""
from typing import Any, cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from domain.entities.exchange_request import ExchangeRequest
from domain.errors import ExchangeRequestAccessDeniedError
from infrastructure.repositories import (
    distributor_dealer_repository as distributor_repo,
)
from infrastructure.repositories import exchange_access_repository as access_repo
from infrastructure.repositories import exchange_request_repository as request_repo


async def require_exchange_company(
    session: AsyncSession, *, user_id: UUID, role: str,
    company_id: UUID | None, write: bool = False,
) -> UUID:
    companies = await access_repo.get_actor_companies(session, user_id, role)
    eligible = [c for c in companies if c["can_view_applications"]
                and (not write or c["can_create_applications"])]
    if company_id is None and len(eligible) == 1:
        return cast("UUID", eligible[0]["id"])
    if company_id is not None and any(c["id"] == company_id for c in eligible):
        return company_id
    raise ExchangeRequestAccessDeniedError()


async def require_lc_request_access(
    session: AsyncSession, request: dict[str, Any], *, user_id: UUID,
    company_id: UUID | None = None, write: bool = False,
) -> UUID:
    company = await require_exchange_company(
        session, user_id=user_id, role="leasing_company", company_id=company_id, write=write,
    )
    ExchangeRequest.from_dict(request).ensure_owned_by_lc(user_id, company)
    return company


async def can_read_exchange_request(
    session: AsyncSession, *, request_id: UUID, user_id: UUID,
    role: str, company_id: UUID | None,
    dealer_company_id: UUID | None = None,
) -> bool:
    if role not in {"leasing_company", "dealer", "distributor"}:
        return False
    try:
        company = await require_exchange_company(
            session, user_id=user_id, role=role, company_id=company_id,
        )
        request = await request_repo.get_by_id(session, request_id)
        if request is None:
            return False
        if role == "leasing_company":
            ExchangeRequest.from_dict(request).ensure_owned_by_lc(user_id, company)
            return True
        dealers = set(await request_repo.list_company_ids_for_request(session, request_id))
        if role == "dealer":
            return company in dealers
        linked = set(await distributor_repo.get_linked_dealer_ids(session, company))
        if dealer_company_id is not None:
            dealers.intersection_update({dealer_company_id})
        return request.get("distributor_id") == company or bool(dealers & linked)
    except ExchangeRequestAccessDeniedError:
        return False


async def require_exchange_bid_access(
    session: AsyncSession, bid: dict[str, Any], *, user_id: UUID,
    role: str, company_id: UUID | None, write: bool = False,
) -> None:
    company = await require_exchange_company(session, user_id=user_id, role=role,
        company_id=company_id, write=write)
    if role == "dealer" and (bid["dealer_id"] != user_id or bid.get("dealer_company_id") not in {None, company}):
        raise ExchangeRequestAccessDeniedError()
    if write and role == "distributor":
        raise ExchangeRequestAccessDeniedError()
    if role == "distributor":
        request = await request_repo.get_by_id(session, bid["request_id"])
        linked = await distributor_repo.get_linked_dealer_ids(session, company)
        if request is None or (request.get("distributor_id") != company and bid.get("dealer_company_id") not in linked):
            raise ExchangeRequestAccessDeniedError()
    if not await can_read_exchange_request(session, request_id=bid["request_id"],
        user_id=user_id, role=role, company_id=company):
        raise ExchangeRequestAccessDeniedError()
