"""Update a cart item (quantity/discount/expiration)."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.services.exchange_supports import (
    resolve_exchange_support_selection,
)
from domain.entities.exchange_cart_item import ExchangeCartItem
from domain.errors import ExchangeCartItemNotFoundError
from infrastructure.repositories import exchange_cart_repository as repo


@dataclass
class UpdateExchangeCartItemCommand:
    item_id: UUID
    user_id: UUID
    quantity: int | None = None
    discount_type: str | None = None
    discount_value: Decimal | None = None
    expiration_at: Any | None = None
    expiration_at_set: bool = False
    # Multi-dealer selection fields (persisted so submit sees the full set).
    warehouses: list[UUID] | None = None
    options: list[UUID] | None = None
    dealer_comment: tuple[UUID, str | None] | None = None
    selected_support_ids: list[UUID] | None = None


async def handle_update_exchange_cart_item(
    cmd: UpdateExchangeCartItemCommand, session: AsyncSession
) -> dict[str, Any]:
    current = await repo.get_by_id(session, cmd.item_id)
    if current is None:
        raise ExchangeCartItemNotFoundError(cmd.item_id)
    entity = ExchangeCartItem.from_dict(current)
    entity.ensure_owned_by(cmd.user_id)

    if cmd.quantity is not None:
        candidate = ExchangeCartItem(quantity=cmd.quantity)
        candidate.ensure_quantity_valid()

    selected_support_ids: list[UUID] | None = None
    if cmd.selected_support_ids is not None:
        selection = await resolve_exchange_support_selection(
            session,
            user_id=cmd.user_id,
            vehicle_id=current["vehicle_id"],
            requested_ids=list(cmd.selected_support_ids),
            select_default=False,
        )
        selected_support_ids = selection.selected_ids

    any_scalar = any(
        v is not None
        for v in (
            cmd.quantity,
            cmd.discount_type,
            cmd.discount_value,
            cmd.expiration_at,
            cmd.selected_support_ids,
        )
    )
    if any_scalar or cmd.expiration_at_set:
        updated = await repo.update_item(
            session,
            cmd.item_id,
            user_id=cmd.user_id,
            quantity=cmd.quantity,
            discount_type=cmd.discount_type,
            discount_value=cmd.discount_value,
            expiration_at=cmd.expiration_at,
            expiration_at_set=cmd.expiration_at_set,
            selected_support_ids=selected_support_ids,
        )
        if not updated:
            raise ExchangeCartItemNotFoundError(cmd.item_id)

    # `warehouses` / `options` use full-replace semantics; `None` leaves the
    # existing rows intact (the frontend only sends the key it changed).
    if cmd.warehouses is not None:
        await repo.set_warehouses(
            session,
            cart_item_id=cmd.item_id,
            warehouse_ids=list(dict.fromkeys(UUID(str(w)) if not isinstance(w, UUID) else w for w in cmd.warehouses)),
        )
    if cmd.options is not None:
        await repo.set_options(
            session,
            cart_item_id=cmd.item_id,
            dealer_option_ids=list(
                dict.fromkeys(UUID(str(o)) if not isinstance(o, UUID) else o for o in cmd.options)
            ),
        )
    if cmd.dealer_comment is not None:
        dealer_id, comment = cmd.dealer_comment
        await repo.upsert_dealer_comment(
            session,
            cart_item_id=cmd.item_id,
            dealer_id=dealer_id,
            comment=comment,
        )

    saved = await repo.get_by_id(session, cmd.item_id)
    assert saved is not None
    return {"message": "Элемент обновлен", "item": saved}
