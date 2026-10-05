"""City repository — async, dict-only API."""
from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.models.vehicles import City
from infrastructure.repository_timing import timed_repository


def _row_to_dict(row: City) -> dict[str, Any]:
    return {
        "id": row.id,
        "name": row.name,
        "created_at": row.created_at,
    }

@timed_repository
async def list_cities(session: AsyncSession) -> list[dict[str, Any]]:
    stmt = select(City).order_by(City.name)
    rows = (await session.execute(stmt)).scalars().all()
    return [_row_to_dict(r) for r in rows]

@timed_repository
async def get_by_id(session: AsyncSession, city_id: UUID) -> dict[str, Any] | None:
    row = await session.get(City, city_id)
    if row is None:
        return None
    return _row_to_dict(row)

@timed_repository
async def name_exists(session: AsyncSession, name: str) -> bool:
    stmt = select(City.id).where(func.lower(City.name) == name.lower())
    result = await session.execute(stmt)
    return result.first() is not None

@timed_repository
async def create_city(session: AsyncSession, *, name: str) -> dict[str, Any]:
    row = City(name=name)
    session.add(row)
    await session.flush()
    return _row_to_dict(row)
