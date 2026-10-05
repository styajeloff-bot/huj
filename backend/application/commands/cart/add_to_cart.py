"""Add a vehicle to the user's cart (upsert-by-user_id+vehicle_id)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from domain.entities.cart_item import CartItem
from domain.errors import VehicleNotFoundError
from domain.storefronts import DEFAULT_CATALOG_SCOPE, CatalogScope
from infrastructure.repositories import cart_repository as repo
from infrastructure.repositories import special_equipment_commerce_repository


@dataclass(frozen=True)
class AddToCartCommand:
    user_id: UUID
    vehicle_id: UUID
    quantity: int = 1
    allow_overstock: bool = False
    scope: CatalogScope = DEFAULT_CATALOG_SCOPE


@dataclass(frozen=True)
class AddToCartResult:
    """Outcome of :func:`handle_add_to_cart`.

    ``created`` is True for a fresh row, False when the quantity of an
    existing ``(user_id, vehicle_id)`` row was incremented.
    """

    cart_item: dict[str, Any]
    created: bool


async def handle_add_to_cart(
    cmd: AddToCartCommand, session: AsyncSession
) -> AddToCartResult:
    CartItem.ensure_quantity_valid(cmd.quantity)

    await repo.lock_cart(session, cmd.user_id, cmd.scope)
    if not await repo.vehicle_exists(session, cmd.vehicle_id, cmd.scope):
        raise VehicleNotFoundError(cmd.vehicle_id)

    existing = await repo.get_cart_item(
        session, cmd.user_id, cmd.vehicle_id, cmd.scope
    )
    quantity = cmd.quantity + (int(existing["quantity"]) if existing else 0)
    allow_overstock = cmd.allow_overstock or bool(existing and existing.get("allow_overstock"))
    product = await special_equipment_commerce_repository.get_product(session, cmd.vehicle_id)
    available_count = 1 if product and product.get("sale_status") == "available" else 0
    CartItem.ensure_stock_quantity(quantity, available=available_count,
                                   allow_overstock=allow_overstock)
    if existing is not None:
        updated = await repo.increment_quantity(
            session,
            cmd.user_id,
            cmd.vehicle_id,
            cmd.quantity,
            cmd.scope,
            allow_overstock=allow_overstock,
        )
        # `existing` guarantees the row is there, so increment cannot return
        # None — assert keeps mypy happy and flags a repo regression fast.
        assert updated is not None
        return AddToCartResult(
            cart_item={
                "cart_id": updated["cart_id"],
                "user_id": cmd.user_id,
                "vehicle_id": cmd.vehicle_id,
                "quantity": updated["quantity"],
                "allow_overstock": allow_overstock,
                "is_selected": updated["is_selected"],
                "added_at": updated["added_at"],
            },
            created=False,
        )

    created = await repo.add_item(
        session, cmd.user_id, cmd.vehicle_id, cmd.quantity, cmd.scope, allow_overstock=allow_overstock
    )
    return AddToCartResult(cart_item=created, created=True)
