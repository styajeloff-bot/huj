"""Dealer option repository — async, dict-only API."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.models.exchange import DealerOption
from infrastructure.repository_timing import timed_repository


def _row_to_dict(row: DealerOption) -> dict[str, Any]:
    return {
        "id": row.id,
        "name": row.name,
        "sort_order": row.sort_order,
        "is_active": bool(row.is_active),
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }

@timed_repository
async def list_active_options(session: AsyncSession) -> list[dict[str, Any]]:
    stmt = (
        select(DealerOption)
        .where(DealerOption.is_active.is_(True))
        .order_by(DealerOption.sort_order.asc(), DealerOption.id.asc())
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [_row_to_dict(r) for r in rows]

@timed_repository
async def list_all_options(session: AsyncSession) -> list[dict[str, Any]]:
    stmt = select(DealerOption).order_by(
        DealerOption.sort_order.asc(), DealerOption.id.asc()
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [_row_to_dict(r) for r in rows]

@timed_repository
async def get_by_id(
    session: AsyncSession, option_id: UUID
) -> dict[str, Any] | None:
    row = await session.get(DealerOption, option_id)
    if row is None:
        return None
    return _row_to_dict(row)

@timed_repository
async def name_exists(
    session: AsyncSession,
    name: str,
    *,
    exclude_id: UUID | None = None,
) -> bool:
    stmt = select(DealerOption.id).where(
        func.lower(DealerOption.name) == name.lower()
    )
    if exclude_id is not None:
        stmt = stmt.where(DealerOption.id != exclude_id)
    result = await session.execute(stmt)
    return result.first() is not None

@timed_repository
async def create_option(
    session: AsyncSession,
    *,
    name: str,
    sort_order: int,
) -> UUID:
    row = DealerOption(name=name, sort_order=sort_order, is_active=True)
    session.add(row)
    await session.flush()
    return row.id

@timed_repository
async def update_option(
    session: AsyncSession,
    option_id: UUID,
    *,
    name: str | None = None,
    sort_order: int | None = None,
    is_active: bool | None = None,
) -> bool:
    row = await session.get(DealerOption, option_id)
    if row is None:
        return False
    if name is not None:
        row.name = name
    if sort_order is not None:
        row.sort_order = sort_order
    if is_active is not None:
        row.is_active = is_active
    cast("Any", row).updated_at = datetime.now(UTC)
    await session.flush()
    return True

@timed_repository
async def deactivate_option(session: AsyncSession, option_id: UUID) -> bool:
    return await update_option(session, option_id, is_active=False)
