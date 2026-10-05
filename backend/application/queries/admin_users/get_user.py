"""Admin: get a single user by id."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from domain.errors import UserNotFoundError
from infrastructure.repositories import admin_users_repository as repo


@dataclass
class GetUserAdminQuery:
    user_id: UUID


async def handle_get_user_admin(
    query: GetUserAdminQuery, session: AsyncSession
) -> dict[str, Any]:
    row = await repo.get_by_id(session, query.user_id)
    if row is None:
        raise UserNotFoundError()
    return cast("dict[str, Any]", row)
