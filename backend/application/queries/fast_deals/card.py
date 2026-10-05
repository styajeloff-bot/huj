"""One deal as the caller may see it."""
from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.fast_deals.actor import Actor
from application.fast_deals.card import build_card

Record = dict[str, Any]


async def handle_get_fast_deal(actor: Actor, deal_id: UUID, session: AsyncSession) -> Record:
    """``{"deal": card}``; a deal the actor may not see is reported as not found."""
    return {"deal": await build_card(session, actor, deal_id)}
