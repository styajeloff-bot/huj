"""Cancellation of an unfinished deal by its initiator (both directions)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.fast_deals import lifecycle
from application.fast_deals.access import load_for_mutation
from application.fast_deals.actor import Actor
from application.fast_deals.card import build_card
from domain.fast_deals.actions import Action
from domain.fast_deals.errors import FastDealValidationError

_MAX_REASON_LENGTH = 2000


@dataclass
class CancelFastDealCommand:
    actor: Actor
    deal_id: UUID
    if_match: str | None
    reason: str | None = None


async def handle_cancel_fast_deal(
    cmd: CancelFastDealCommand, session: AsyncSession
) -> dict[str, Any]:
    """Cancel is final: reservations are released and the deal is closed for editing.

    Only the initiator cancels. In DL a split part is cancelled on its own; the other
    parts of the group are separate deals and stay untouched.
    """
    ctx = await load_for_mutation(session, cmd.actor, cmd.deal_id, cmd.if_match)
    ctx.require_initiator()
    ctx.require(Action.CANCEL, "Сделка уже завершена и не может быть отменена")
    reason = (cmd.reason or "").strip() or None
    if reason is not None and len(reason) > _MAX_REASON_LENGTH:
        raise FastDealValidationError(
            f"Причина не должна быть длиннее {_MAX_REASON_LENGTH} символов", field="reason"
        )
    await lifecycle.cancel_deal(session, ctx, reason=reason)
    return {"deal": await build_card(session, cmd.actor, ctx.deal_id)}
