"""Global reserve of catalog units for fast deals (implemented by the claims owner).

Contract used by every flow:

* ``reserve_deal`` runs under the deal lock inside the send transaction. It locks all
  reservable products in a stable order, validates every claim (allocations of other
  deals/applications, purchases, other fast deals) and inserts one allocation per
  position with ``reserved_until = NULL``. Any failure raises
  ``FastDealReserveConflictError`` and the whole send is rolled back.
* ``release_*`` frees allocations in the same transaction as the status change.
* ``complete_deal`` completes allocations and marks products sold at confirmation.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.fast_deals.actor import Actor

Record = dict[str, Any]


async def reserve_deal(
    session: AsyncSession, deal: Record, vehicles: list[Record], actor: Actor
) -> None:
    """Reserve every ``is_reservable`` active position of the deal."""
    raise NotImplementedError


async def release_deal(session: AsyncSession, deal_id: UUID, *, reason: str) -> None:
    """Release every active allocation of the deal; completed ones are untouched."""
    raise NotImplementedError


async def release_vehicle(session: AsyncSession, vehicle_id: UUID, *, reason: str) -> None:
    """Release the allocation of one position (removal or replacement)."""
    raise NotImplementedError


async def complete_deal(session: AsyncSession, deal_id: UUID) -> None:
    """Complete the deal's allocations and mark their products ``sold``."""
    raise NotImplementedError
