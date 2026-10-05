"""Delete (soft-deactivate) dealer option command."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from domain.errors import DealerOptionNotFoundError
from infrastructure.repositories import dealer_option_repository as repo


@dataclass
class DeleteDealerOptionCommand:
    option_id: UUID


async def handle_delete_dealer_option(
    cmd: DeleteDealerOptionCommand, session: AsyncSession
) -> dict[str, Any]:
    existing = await repo.get_by_id(session, cmd.option_id)
    if existing is None:
        raise DealerOptionNotFoundError(cmd.option_id)
    await repo.deactivate_option(session, cmd.option_id)
    return {"message": "Опция деактивирована"}
