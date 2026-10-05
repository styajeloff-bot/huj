"""Update the current dealer's profile.

Dealer profile is a joined view of ``users`` + ``companies`` — the
command therefore dispatches two partial updates via the dealer
repository. Returns the refreshed profile dict so the router can echo it
back to the client.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from domain.errors import UserNotFoundError
from infrastructure.repositories import dealer_repository as repo


@dataclass(frozen=True)
class UpdateDealerProfileCommand:
    user_id: UUID
    user_fields: dict[str, Any] = field(default_factory=dict)
    company_fields: dict[str, Any] = field(default_factory=dict)


async def handle_update_dealer_profile(
    cmd: UpdateDealerProfileCommand, session: AsyncSession
) -> dict[str, Any]:
    existing = await repo.get_dealer_user(session, cmd.user_id)
    if existing is None:
        raise UserNotFoundError()

    if cmd.user_fields:
        await repo.update_dealer_user(session, cmd.user_id, cmd.user_fields)

    company_id = existing["user"]["company_id"]
    if cmd.company_fields and company_id:
        await repo.update_dealer_company(session, company_id, cmd.company_fields)

    refreshed = await repo.get_dealer_user(session, cmd.user_id)
    if refreshed is None:
        raise UserNotFoundError()
    return cast("dict[str, Any]", refreshed)
