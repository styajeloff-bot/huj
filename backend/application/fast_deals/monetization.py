"""Monetization capture of a confirmed deal (implemented by the monetization owner)."""
from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from application.fast_deals.actor import Actor

Record = dict[str, Any]


async def capture_confirmed_deal(session: AsyncSession, deal: Record, actor: Actor) -> None:
    """Capture once on the single transition to ``confirmed``.

    A capture failure is logged and notified by the existing policy and never undoes
    the already valid business confirmation.
    """
    raise NotImplementedError
