"""Positions repository — async, dict-only API."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, TypedDict
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.models.positions import Position
from infrastructure.repository_timing import timed_repository


class PositionDict(TypedDict):
    id: str
    name: str
    code: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


def _to_dict(pos: Position) -> dict[str, Any]:
    return {
        "id": str(pos.id),
        "name": pos.name,
        "code": pos.code,
        "is_active": bool(pos.is_active),
        "created_at": pos.created_at,
        "updated_at": pos.updated_at,
    }


@timed_repository
async def list_positions(
    session: AsyncSession,
    only_active: bool = False,
) -> list[dict[str, Any]]:
    """Return all positions ordered by name. Optionally filter by is_active=True."""
    stmt = sa.select(Position)
    if only_active:
        stmt = stmt.where(Position.is_active.is_(True))
    stmt = stmt.order_by(Position.name.asc(), Position.id.asc())
    rows = (await session.execute(stmt)).scalars().all()
    return [_to_dict(row) for row in rows]


@timed_repository
async def get_position_by_id(
    session: AsyncSession,
    position_id: UUID,
) -> dict[str, Any] | None:
    """Return position by primary key ID or None if not found."""
    row = await session.get(Position, position_id)
    if row is None:
        return None
    return _to_dict(row)


@timed_repository
async def get_position_by_code(
    session: AsyncSession,
    code: str,
) -> dict[str, Any] | None:
    """Return position by unique code or None if not found."""
    stmt = sa.select(Position).where(Position.code == code)
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        return None
    return _to_dict(row)


@timed_repository
async def create_position(
    session: AsyncSession,
    name: str,
    code: str,
    is_active: bool = True,
) -> dict[str, Any]:
    """Create a new position and flush changes."""
    pos = Position(
        name=name,
        code=code,
        is_active=is_active,
    )
    session.add(pos)
    await session.flush()
    await session.refresh(pos)
    return _to_dict(pos)


@timed_repository
async def update_position(
    session: AsyncSession,
    position_id: UUID,
    name: str,
    code: str,
    is_active: bool,
) -> dict[str, Any] | None:
    """Update position name, code, is_active, and updated_at. Preserves created_at."""
    pos = await session.get(Position, position_id)
    if pos is None:
        return None
    pos.name = name
    pos.code = code
    pos.is_active = is_active
    pos.updated_at = datetime.now(UTC)
    await session.flush()
    return _to_dict(pos)


@timed_repository
async def deactivate_position(
    session: AsyncSession,
    position_id: UUID,
) -> dict[str, Any] | None:
    """Set is_active=False and update updated_at."""
    pos = await session.get(Position, position_id)
    if pos is None:
        return None
    pos.is_active = False
    pos.updated_at = datetime.now(UTC)
    await session.flush()
    return _to_dict(pos)
