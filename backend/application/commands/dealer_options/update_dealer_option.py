"""Update dealer option command."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from domain.entities.dealer_option import DealerOption
from domain.errors import (
    DealerOptionAlreadyExistsError,
    DealerOptionNotFoundError,
)
from infrastructure.repositories import dealer_option_repository as repo


@dataclass
class UpdateDealerOptionCommand:
    option_id: UUID
    name: str | None = None
    sort_order: int | None = None
    is_active: bool | None = None


async def handle_update_dealer_option(
    cmd: UpdateDealerOptionCommand, session: AsyncSession
) -> dict[str, Any]:
    existing = await repo.get_by_id(session, cmd.option_id)
    if existing is None:
        raise DealerOptionNotFoundError(cmd.option_id)

    merged_name = cmd.name if cmd.name is not None else existing["name"]
    merged_sort = (
        cmd.sort_order if cmd.sort_order is not None else existing["sort_order"]
    )
    merged_active = (
        cmd.is_active if cmd.is_active is not None else existing["is_active"]
    )

    option = DealerOption(
        option_id=cmd.option_id,
        name=merged_name,
        sort_order=int(merged_sort or 0),
        is_active=bool(merged_active),
    )
    option.ensure_valid()

    if cmd.name is not None and await repo.name_exists(
        session, option.name, exclude_id=cmd.option_id
    ):
        raise DealerOptionAlreadyExistsError(option.name)

    await repo.update_option(
        session,
        cmd.option_id,
        name=option.name if cmd.name is not None else None,
        sort_order=option.sort_order if cmd.sort_order is not None else None,
        is_active=option.is_active if cmd.is_active is not None else None,
    )
    saved = await repo.get_by_id(session, cmd.option_id)
    assert saved is not None
    return cast("dict[str, Any]", saved)
