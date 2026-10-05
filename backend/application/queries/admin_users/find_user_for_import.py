"""Find user by id or phone for CSV import upsert."""
from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.repositories.admin_users_repository import (
    get_by_id,
    get_by_phone,
)


async def find_user_by_id(
    session: AsyncSession, user_id: UUID
) -> dict[str, Any] | None:
    result: dict[str, Any] | None = await get_by_id(session, user_id)
    return result


async def find_user_by_phone(
    session: AsyncSession, phone: str
) -> dict[str, Any] | None:
    result: dict[str, Any] | None = await get_by_phone(session, phone)
    return result
