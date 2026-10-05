"""Remove a single item from the exchange cart."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from domain.errors import ExchangeCartItemNotFoundError
from infrastructure.repositories import exchange_cart_repository as repo


@dataclass
class RemoveExchangeCartItemCommand:
    item_id: UUID
    user_id: UUID


async def handle_remove_exchange_cart_item(
    cmd: RemoveExchangeCartItemCommand, session: AsyncSession
) -> dict[str, Any]:
    removed = await repo.remove_item(
        session, cmd.item_id, user_id=cmd.user_id
    )
    if not removed:
        raise ExchangeCartItemNotFoundError(cmd.item_id)
    return {"message": "Элемент удален из корзины"}
