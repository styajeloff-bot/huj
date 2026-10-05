
"""Update a bid (dealer-owned)."""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.common import _isoformat
from application.services.exchange_access import (
    can_read_exchange_request,
    require_exchange_company,
)
from application.services.exchange_notification_events import record_exchange_event
from domain.entities.exchange_bid import ExchangeBid
from domain.entities.exchange_request import ExchangeRequest
from domain.errors import (
    ExchangeBidNotFoundError,
    ExchangeRequestNotFoundError,
)
from infrastructure.messaging.dwh_events import emit_exchange_bid_changed
from infrastructure.repositories import (
    exchange_bid_repository as bid_repo,
)
from infrastructure.repositories import (
    exchange_request_repository as req_repo,
)


@dataclass
class UpdateBidCommand:
    bid_id: UUID
    dealer_id: UUID
    company_id: UUID | None = field(default=None, kw_only=True)
    price: Decimal | None = None
    quantity: int | None = None
    comment: str | None = None
    dealer_option_ids: list[UUID] | None = None


async def handle_update_bid(
    cmd: UpdateBidCommand, session: AsyncSession
) -> dict[str, Any]:
    current = await bid_repo.get_by_id(session, cmd.bid_id)
    if current is None:
        raise ExchangeBidNotFoundError(cmd.bid_id)

    bid = ExchangeBid.from_dict(current)
    bid.ensure_owned_by_dealer(cmd.dealer_id)
    company_id = await require_exchange_company(session, user_id=cmd.dealer_id,
        role="dealer", company_id=cmd.company_id, write=True)
    if current.get("dealer_company_id") not in {None, company_id} or not await can_read_exchange_request(
        session, request_id=bid.request_id, user_id=cmd.dealer_id, role="dealer", company_id=company_id,
    ):
        from domain.errors import ExchangeRequestAccessDeniedError
        raise ExchangeRequestAccessDeniedError()

    req_raw = await req_repo.lock_request(session, bid.request_id)
    if req_raw is None:
        raise ExchangeRequestNotFoundError(bid.request_id)
    request = ExchangeRequest.from_dict(req_raw)
    request.ensure_can_receive_bid()
    current = await bid_repo.get_by_id(session, cmd.bid_id)
    if current is None:
        raise ExchangeBidNotFoundError(cmd.bid_id)

    max_qty = max(int(request.quantity or 1), 1)
    new_qty: int | None = None
    if cmd.quantity is not None:
        new_qty = max(1, min(max_qty, cmd.quantity))

    if cmd.price is not None:
        candidate = ExchangeBid(price=cmd.price)
        candidate.ensure_valid_price()

    await bid_repo.update_bid(
        session,
        cmd.bid_id,
        price=cmd.price,
        quantity=new_qty,
        comment=cmd.comment,
    )

    if cmd.dealer_option_ids is not None:
        current["dealer_option_ids"] = [row["dealer_option_id"] for row in await bid_repo.list_options(session, cmd.bid_id)]
        await bid_repo.set_options(
            session,
            bid_id=cmd.bid_id,
            dealer_option_ids=cmd.dealer_option_ids,
        )

    saved = await bid_repo.get_by_id(session, cmd.bid_id)
    assert saved is not None
    if cmd.dealer_option_ids is not None:
        saved["dealer_option_ids"] = cmd.dealer_option_ids
    await record_exchange_event(session, event_type="exchange.bid_updated", request=req_raw,
        bid=saved, previous=current, actor_user_id=cmd.dealer_id)
    emit_exchange_bid_changed({
        "bid_id": cmd.bid_id,
        "request_id": saved.get("request_id"),
        "dealer_id": saved.get("dealer_id"),
        "price": str(saved.get("price")) if saved.get("price") is not None else None,
        "comment": saved.get("comment"),
        "is_accepted": bool(saved.get("is_accepted")),
        "kp_file_url": saved.get("kp_file_url"),
        "kp_file_name": saved.get("kp_file_name"),
        "kp_status": saved.get("kp_status"),
        "kp_dealer_comment": saved.get("kp_dealer_comment"),
        "kp_sent_at": _isoformat(saved.get("kp_sent_at")),
        "kp_responded_at": _isoformat(saved.get("kp_responded_at")),
        "quantity": saved.get("quantity"),
        "bid_file_url": saved.get("bid_file_url"),
        "bid_file_name": saved.get("bid_file_name"),
        "created_at": _isoformat(saved.get("created_at")),
        "updated_at": _isoformat(saved.get("updated_at")),
        "_deleted": False,
    })
    return {"message": "Ставка обновлена", "bid": saved}
