"""Withdraw an own, still-open bid and durably record its immutable snapshot."""
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.services.exchange_access import require_exchange_bid_access
from application.services.exchange_notification_events import record_exchange_event
from domain.entities.exchange_bid import ExchangeBid
from domain.entities.exchange_request import ExchangeRequest
from domain.errors import (
    ExchangeBidNotFoundError,
    ExchangeRequestNotFoundError,
)
from infrastructure.repositories import exchange_bid_repository as bid_repo
from infrastructure.repositories import exchange_request_repository as request_repo


@dataclass
class WithdrawBidCommand:
    bid_id: UUID
    user_id: UUID
    company_id: UUID | None = None


async def handle_withdraw_bid(cmd: WithdrawBidCommand, session: AsyncSession) -> None:
    bid = await bid_repo.get_by_id(session, cmd.bid_id)
    if bid is None:
        raise ExchangeBidNotFoundError(cmd.bid_id)
    request = await request_repo.lock_request(session, bid["request_id"])
    if request is None:
        raise ExchangeRequestNotFoundError(bid["request_id"])
    bid = await bid_repo.get_by_id(session, cmd.bid_id)
    if bid is None:
        raise ExchangeBidNotFoundError(cmd.bid_id)
    await require_exchange_bid_access(session, bid, user_id=cmd.user_id,
        role="dealer", company_id=cmd.company_id, write=True)
    ExchangeRequest.from_dict(request).ensure_can_receive_bid()
    ExchangeBid.from_dict(bid).ensure_can_withdraw()
    await record_exchange_event(session, event_type="exchange.bid_withdrawn",
        request=request, bid=bid, actor_user_id=cmd.user_id)
    await bid_repo.delete_bid(session, cmd.bid_id)
