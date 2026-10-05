
"""LC approves a dealer bid — KP flow finalization.

Sets ``is_accepted=true`` on the bid, records ``accepted_bid_id`` on the
request and moves the request to ``deal``. The bid must have KP=accepted
and the request must still be ``open`` with no other accepted bid.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.commands.exchange.finalize_supports import (
    finalize_exchange_supports,
)
from application.commands.monetization.integration import capture_source_transition
from application.common import _isoformat
from application.services.exchange_access import require_lc_request_access
from application.services.exchange_dates import dwh_expiration_date
from application.services.exchange_notification_events import record_exchange_event
from domain.entities.exchange_bid import ExchangeBid
from domain.entities.exchange_request import STATUS_DEAL, ExchangeRequest
from domain.errors import (
    BidAlreadyAcceptedError,
    ExchangeBidNotFoundError,
    ExchangeRequestNotFoundError,
)
from infrastructure.messaging.dwh_events import (
    emit_exchange_bid_changed,
    emit_exchange_request_changed,
)
from infrastructure.repositories import (
    exchange_bid_repository as bid_repo,
)
from infrastructure.repositories import (
    exchange_request_repository as req_repo,
)


@dataclass
class ApproveBidCommand:
    bid_id: UUID
    lc_user_id: UUID
    company_id: UUID | None = field(default=None, kw_only=True)


async def handle_approve_bid(
    cmd: ApproveBidCommand, session: AsyncSession
) -> dict[str, Any]:
    bid_raw = await bid_repo.get_by_id(session, cmd.bid_id)
    if bid_raw is None:
        raise ExchangeBidNotFoundError(cmd.bid_id)

    bid = ExchangeBid.from_dict(bid_raw)

    req_raw = await req_repo.lock_request(session, bid.request_id)
    if req_raw is None:
        raise ExchangeRequestNotFoundError(bid.request_id)
    bid_raw = await bid_repo.get_by_id(session, cmd.bid_id)
    if bid_raw is None:
        raise ExchangeBidNotFoundError(cmd.bid_id)
    bid = ExchangeBid.from_dict(bid_raw)
    request = ExchangeRequest.from_dict(req_raw)
    await require_lc_request_access(session, req_raw, user_id=cmd.lc_user_id, company_id=cmd.company_id, write=True)

    # Reject if any other bid on the same request is already accepted.
    siblings = await bid_repo.list_for_request(
        session, request_id=bid.request_id
    )
    if any(
        other["id"] != bid.id and bool(other["is_accepted"])
        for other in siblings
    ):
        raise BidAlreadyAcceptedError()

    request.ensure_can_accept_bid()
    bid.ensure_can_approve()

    await bid_repo.set_is_accepted(
        session, cmd.bid_id, is_accepted=True
    )
    await req_repo.set_status(
        session,
        bid.request_id,
        status=STATUS_DEAL,
        accepted_bid_id=cmd.bid_id,
    )
    await finalize_exchange_supports(
        session,
        request_id=bid.request_id,
        accepted_bid=bid_raw,
        actor_id=cmd.lc_user_id,
    )
    await capture_source_transition(session, actor_user_id=cmd.lc_user_id,
                                    exchange_request_id=bid.request_id)
    from infrastructure.messaging.status_events import (
        emit_exchange_bid_status_changed,
        emit_exchange_request_status_changed,
    )
    emit_exchange_request_status_changed(
        request_id=bid.request_id,
        old_status=request.status,
        new_status=STATUS_DEAL,
        changed_by=cmd.lc_user_id,
        payload={"accepted_bid_id": cmd.bid_id},
    )
    emit_exchange_bid_status_changed(
        bid_id=bid.id,
        old_status=bid.kp_status,
        new_status="accepted",
        changed_by=cmd.lc_user_id,
    )

    req_saved = await req_repo.get_by_id(session, bid.request_id)
    if req_saved is not None:
        await record_exchange_event(session, event_type="exchange.request_finalized", request=req_saved,
            previous=req_raw, actor_user_id=cmd.lc_user_id)
        await record_exchange_event(session, event_type="exchange.bid_selected", request=req_saved,
            bid=bid_raw, actor_user_id=cmd.lc_user_id,
            payload={"selected_dealer_company_id": str(bid_raw["dealer_company_id"]) if bid_raw.get("dealer_company_id") else None})
        await record_exchange_event(session, event_type="exchange.bid_not_selected", request=req_saved,
            bid=bid_raw, actor_user_id=cmd.lc_user_id,
            payload={"selected_dealer_company_id": str(bid_raw["dealer_company_id"]) if bid_raw.get("dealer_company_id") else None})
        emit_exchange_request_changed({
            "request_id": bid.request_id,
            "lc_user_id": req_saved.get("lc_user_id"),
            "vehicle_id": req_saved.get("vehicle_id"),
            "quantity": req_saved.get("quantity"),
            "expiration_date": dwh_expiration_date(req_saved.get("expiration_at")),
            "discount_type": req_saved.get("discount_type"),
            "discount_value": str(req_saved.get("discount_value")) if req_saved.get("discount_value") is not None else None,
            "file_url": req_saved.get("file_url"),
            "file_name": req_saved.get("file_name"),
            "status": req_saved.get("status"),
            "accepted_bid_id": req_saved.get("accepted_bid_id"),
            "batch_number": req_saved.get("batch_number"),
            "batch_index": req_saved.get("batch_index"),
            "created_at": _isoformat(req_saved.get("created_at")),
            "updated_at": _isoformat(req_saved.get("updated_at")),
            "_deleted": False,
        })

    saved = await bid_repo.get_by_id(session, cmd.bid_id)
    assert saved is not None
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
    return {"message": "Ставка принята, сделка оформлена", "bid": saved}
