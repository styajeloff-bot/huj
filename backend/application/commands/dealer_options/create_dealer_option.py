"""Create dealer option command."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from sqlalchemy.ext.asyncio import AsyncSession

from domain.entities.dealer_option import DealerOption
from domain.errors import DealerOptionAlreadyExistsError
from infrastructure.repositories import dealer_option_repository as repo


@dataclass
class CreateDealerOptionCommand:
    name: str
    sort_order: int = 0


async def handle_create_dealer_option(
    cmd: CreateDealerOptionCommand, session: AsyncSession
) -> dict[str, Any]:
    option = DealerOption(
        option_id=None,
        name=cmd.name,
        sort_order=cmd.sort_order,
    )
    option.ensure_valid()

    if await repo.name_exists(session, option.name):
        raise DealerOptionAlreadyExistsError(option.name)

    option_id = await repo.create_option(
        session, name=option.name, sort_order=option.sort_order
    )
    saved = await repo.get_by_id(session, option_id)
    assert saved is not None
    return cast("dict[str, Any]", saved)
