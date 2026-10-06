"""Monetization capture of a confirmed deal."""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from application.commands.monetization.integration import capture_source_transition
from application.fast_deals.actor import Actor

logger = logging.getLogger("carcraft-backend")

Record = dict[str, Any]


async def capture_confirmed_deal(session: AsyncSession, deal: Record, actor: Actor) -> None:
    """Capture once on the single transition to ``confirmed``.

    A capture failure is logged and notified by the existing policy and never undoes
    the already valid business confirmation. The monetization module reads the deal
    itself (confirmed amount, parties, positions, applied supports) under the deal
    lock the caller holds, and is idempotent per deal id, so a replay creates nothing.
    The outer savepoint additionally keeps the confirmation transaction usable when
    even the failure notification cannot be written.
    """
    try:
        async with session.begin_nested():
            await capture_source_transition(
                session, actor_user_id=actor.user_id, fast_deal_id=deal["id"]
            )
    except Exception:
        logger.exception("fast_deal_monetization_capture_failed fast_deal_id=%s", deal["id"])
