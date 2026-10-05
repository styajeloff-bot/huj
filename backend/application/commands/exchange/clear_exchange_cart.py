"""Clear the current user's exchange cart."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.repositories import exchange_cart_repository as repo


@dataclass
class ClearExchangeCartCommand:
    user_id: UUID


async def handle_clear_exchange_cart(
    cmd: ClearExchangeCartCommand, session: AsyncSession
) -> dict[str, Any]:
    deleted = await repo.clear_cart(session, cmd.user_id)
    return {"message": "Корзина очищена", "deleted_count": deleted}
