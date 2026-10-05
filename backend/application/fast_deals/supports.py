"""Support programs, support requests and compensations (implemented by the supports owner)."""
from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from application.fast_deals.actor import Actor

Record = dict[str, Any]


async def create_compensations_on_confirm(
    session: AsyncSession, deal: Record, actor: Actor
) -> None:
    """Create compensations of the deal's applied programs once, at confirmation.

    Compensations use source ``fast_deal`` through the existing applied-support and
    compensation mechanism. A repeated call creates nothing new.
    """
    raise NotImplementedError
