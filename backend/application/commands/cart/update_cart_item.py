"""Partial update of a single cart item.

Replaces the three sub-field commands (quantity / price / comment) plus
the standalone is_selected toggle with one command whose payload carries
any subset of mutable fields. Omitted fields (``None``) are left as-is,
except for ``comment`` where ``None`` is treated as *not provided* and
an empty-string value clears the comment (matches the previous semantics).
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from domain.entities.cart_item import CartItem
from domain.errors import CartItemNotFoundError
from domain.storefronts import DEFAULT_CATALOG_SCOPE, CatalogScope
from infrastructure.repositories import cart_repository as repo
from infrastructure.repositories import special_equipment_commerce_repository

# Sentinel used to distinguish "field not provided" from "field set to null".
_UNSET: Any = object()


@dataclass(frozen=True)
class UpdateCartItemCommand:
    user_id: UUID
    vehicle_id: UUID
    role: str | None = None
    is_selected: bool | None = None
    quantity: int | None = None
    allow_overstock: bool | None = None
    comment: Any = _UNSET  # str | None | _UNSET (None clears the value)
    custom_price: Any = _UNSET  # Decimal | None | _UNSET
    equipments: Any = _UNSET  # list[dict] | _UNSET
    services: Any = _UNSET  # list[dict] | _UNSET
    scope: CatalogScope = DEFAULT_CATALOG_SCOPE


async def handle_update_cart_item(
    cmd: UpdateCartItemCommand, session: AsyncSession
) -> dict[str, Any]:
    if cmd.quantity is not None:
        CartItem.ensure_quantity_valid(cmd.quantity)
    await repo.lock_cart(session, cmd.user_id, cmd.scope)
    existing = await repo.get_cart_item(
        session, cmd.user_id, cmd.vehicle_id, cmd.scope
    )
    if existing is None:
        raise CartItemNotFoundError(cmd.vehicle_id)

    quantity = cmd.quantity if cmd.quantity is not None else int(existing["quantity"])
    allow_overstock = cmd.allow_overstock if cmd.allow_overstock is not None else bool(existing.get("allow_overstock"))
    if cmd.quantity is not None or cmd.allow_overstock is not None:
        product = await special_equipment_commerce_repository.get_product(session, cmd.vehicle_id)
        available_count = 1 if product and product.get("sale_status") == "available" else 0
        CartItem.ensure_stock_quantity(quantity, available=available_count,
                                       allow_overstock=allow_overstock)

    if cmd.custom_price is not _UNSET:
        CartItem.ensure_custom_price_allowed(
            cmd.role,
            existing.get("base_price"),
            vehicle_exists=existing.get("vehicle_row_id") is not None,
        )

    if cmd.is_selected is not None:
        await repo.update_selection(
            session,
            cmd.user_id,
            cmd.vehicle_id,
            cmd.is_selected,
            cmd.scope,
        )
    if cmd.quantity is not None or cmd.allow_overstock is not None:
        await repo.update_quantity(
            session,
            cmd.user_id,
            cmd.vehicle_id,
            quantity,
            cmd.scope,
            allow_overstock=allow_overstock,
        )
    if cmd.custom_price is not _UNSET:
        custom_price: Decimal | None = cmd.custom_price
        await repo.update_custom_price(
            session,
            cmd.user_id,
            cmd.vehicle_id,
            custom_price,
            cmd.scope,
        )
    if cmd.comment is not _UNSET:
        # Normalize empty string → NULL (matches the previous comment
        # endpoint's semantics).
        comment_value: str | None = cmd.comment if cmd.comment else None
        await repo.update_comment(
            session,
            cmd.user_id,
            cmd.vehicle_id,
            comment_value,
            cmd.scope,
        )
    if cmd.equipments is not _UNSET or cmd.services is not _UNSET:
        await repo.update_additional_options(
            session,
            cmd.user_id,
            cmd.vehicle_id,
            cmd.scope,
            equipments=cmd.equipments if cmd.equipments is not _UNSET else None,
            services=cmd.services if cmd.services is not _UNSET else None,
        )

    fresh = await repo.get_cart_item(
        session, cmd.user_id, cmd.vehicle_id, cmd.scope
    )
    assert fresh is not None
    return dict(fresh)


__all__ = ["UpdateCartItemCommand", "handle_update_cart_item"]
