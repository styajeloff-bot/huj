"""Add a comment to a bid (LC or dealer, within their access scope)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.services.exchange_access import require_exchange_bid_access
from domain.entities.exchange_bid import ExchangeBid
from domain.errors import (
    ExchangeBidAccessDeniedError,
    ExchangeBidNotFoundError,
    ExchangeRequestNotFoundError,
)
from infrastructure.repositories import (
    exchange_bid_repository as bid_repo,
)
from infrastructure.repositories import (
    exchange_request_repository as req_repo,
)


@dataclass
class AddBidCommentCommand:
    bid_id: UUID
    user_id: UUID
    user_role: str
    comment: str
    company_id: UUID | None = None


async def handle_add_bid_comment(
    cmd: AddBidCommentCommand, session: AsyncSession
) -> dict[str, Any]:
    bid_raw = await bid_repo.get_by_id(session, cmd.bid_id)
    if bid_raw is None:
        raise ExchangeBidNotFoundError(cmd.bid_id)
    bid = ExchangeBid.from_dict(bid_raw)

    req_raw = await req_repo.get_by_id(session, bid.request_id)
    if req_raw is None:
        raise ExchangeRequestNotFoundError(bid.request_id)

    if cmd.user_role == "leasing_company":
        await require_exchange_bid_access(session, bid_raw, user_id=cmd.user_id,
            role=cmd.user_role, company_id=cmd.company_id, write=True)
    elif cmd.user_role == "dealer":
        bid.ensure_owned_by_dealer(cmd.user_id)
        await require_exchange_bid_access(session, bid_raw, user_id=cmd.user_id,
            role=cmd.user_role, company_id=cmd.company_id, write=True)
    elif cmd.user_role != "carcraft_employee":
        raise ExchangeBidAccessDeniedError()

    comment = await bid_repo.add_comment(
        session,
        bid_id=cmd.bid_id,
        user_id=cmd.user_id,
        comment=cmd.comment,
    )
    return {
        "message": "Комментарий добавлен",
        "comment": comment,
    }
