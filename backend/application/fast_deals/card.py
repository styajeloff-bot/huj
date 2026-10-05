"""Role-scoped card of a deal (implemented by the queries owner)."""
from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.fast_deals.actor import Actor

Record = dict[str, Any]


async def build_card(session: AsyncSession, actor: Actor, deal_id: UUID) -> Record:
    """The card as the actor may see it: projection, ``allowed_actions``, ``etag``.

    Raises ``FastDealNotFoundError`` when the actor may not see the deal.
    """
    raise NotImplementedError
