
"""Create a bid on an exchange request (dealer-owned)."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.common import _isoformat
from application.services.exchange_access import require_exchange_company
from application.services.exchange_notification_events import record_exchange_event
from domain.entities.exchange_bid import ExchangeBid
from domain.entities.exchange_request import ExchangeRequest
from domain.errors import (
    BidAlreadyExistsError,
    ExchangeRequestNotFoundError,
)
from infrastructure.messaging.dwh_events import emit_exchange_bid_changed
from infrastructure.repositories import (
    exchange_bid_repository as bid_repo,
)
from infrastructure.repositories import (
    exchange_request_repository as req_repo,
)

logger = logging.getLogger("carcraft-backend")


@dataclass
class CreateBidCommand:
    request_id: UUID
    dealer_id: UUID
    price: Decimal
    quantity: int = 1
    comment: str | None = None
    dealer_option_ids: list[UUID] = field(default_factory=list)
    company_id: UUID | None = None


async def handle_create_bid(
    cmd: CreateBidCommand, session: AsyncSession
) -> dict[str, Any]:
    company_id = await require_exchange_company(session, user_id=cmd.dealer_id,
        role="dealer", company_id=cmd.company_id, write=True)
    req_raw = await req_repo.lock_request(session, cmd.request_id)
    if req_raw is None:
        raise ExchangeRequestNotFoundError(cmd.request_id)
    company_ids = await req_repo.list_company_ids_for_request(
        session, cmd.request_id
    )

    if company_id not in company_ids:
        from domain.errors import ExchangeRequestAccessDeniedError
        raise ExchangeRequestAccessDeniedError()

    request = ExchangeRequest.from_dict({**req_raw, "dealer_ids": company_ids})
    request.ensure_can_receive_bid()

    existing = await bid_repo.find_by_request_and_dealer(
        session, request_id=cmd.request_id, dealer_id=cmd.dealer_id
    )
    if existing is not None:
        logger.info(
            "exchange create_bid: 409 — bid already exists "
            "(bid_id=%s, request_id=%s, dealer_id=%s). "
            "Dealer must PUT /exchange/bids/%s to update instead.",
            existing.get("id"), cmd.request_id, cmd.dealer_id,
            existing.get("id"),
        )
        raise BidAlreadyExistsError()

    max_qty = max(int(request.quantity or 1), 1)
    quantity = max(1, min(max_qty, cmd.quantity))

    bid_entity = ExchangeBid(
        id=UUID(int=0),
        request_id=cmd.request_id,
        dealer_id=cmd.dealer_id,
        price=cmd.price,
        quantity=quantity,
        comment=cmd.comment,
    )
    bid_entity.ensure_valid_price()
    bid_entity.ensure_quantity_in_range(max_qty)

    bid_id = await bid_repo.create_bid(
        session,
        request_id=cmd.request_id,
        dealer_id=cmd.dealer_id,
        dealer_company_id=company_id,
        price=cmd.price,
        quantity=quantity,
        comment=cmd.comment,
    )
    from infrastructure.messaging.status_events import emit_exchange_bid_status_changed
    emit_exchange_bid_status_changed(
        bid_id=bid_id,
        old_status=None,
        new_status="none",
        changed_by=cmd.dealer_id,
        payload={"price": str(cmd.price), "quantity": quantity},
    )
    if cmd.dealer_option_ids:
        await bid_repo.set_options(
            session,
            bid_id=bid_id,
            dealer_option_ids=cmd.dealer_option_ids,
        )

    saved = await bid_repo.get_by_id(session, bid_id)
    assert saved is not None
    await record_exchange_event(session, event_type="exchange.bid_created", request=req_raw,
        bid=saved, actor_user_id=cmd.dealer_id)
    emit_exchange_bid_changed({
        "bid_id": bid_id,
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
    return {"message": "Ставка создана", "bid": saved}
