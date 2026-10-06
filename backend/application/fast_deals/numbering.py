"""Allocation of the immutable deal number."""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from domain.fast_deals import numbering
from domain.fast_deals.values import SourceType
from infrastructure.repositories import fast_deal_repository as repo


async def allocate_display_number(
    session: AsyncSession, source_type: SourceType | str, client_inn: str
) -> str:
    """``DD-<INN>-<DDMMYY>-<NNN>`` for the UTC day, under an advisory lock.

    The lock serialises concurrent creations of one direction, client and day; the
    unique index remains the last defence. The caller owns the transaction, so a
    rolled-back creation leaves no gap-forcing state behind.
    """
    day = datetime.now(UTC).date()
    inn = numbering.normalize_client_inn(client_inn)
    await repo.acquire_number_lock(session, numbering.lock_key(source_type, inn, day))
    prefix = numbering.number_prefix(source_type, inn, day)
    sequence = await repo.max_number_sequence(session, prefix) + 1
    return numbering.format_number(source_type, inn, day, sequence)
