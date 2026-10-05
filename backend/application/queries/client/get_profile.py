"""Query: fetch the current user's profile (users + client_profiles)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from domain.errors import UserNotFoundError
from infrastructure.repositories import client_repository as repo


@dataclass(frozen=True)
class GetClientProfileQuery:
    user_id: UUID


async def handle_get_client_profile(
    query: GetClientProfileQuery, session: AsyncSession
) -> dict[str, Any]:
    profile = await repo.get_profile_with_user(session, query.user_id)
    if profile is None:
        raise UserNotFoundError()
    return cast("dict[str, Any]", profile)
