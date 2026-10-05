"""Idempotently transfer one persisted guest-cart row."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from domain.entities.cart_item import CartItem
from domain.errors import GuestCartTransferConflictError, VehicleNotFoundError
from domain.storefronts import DEFAULT_CATALOG_SCOPE, CatalogScope
from infrastructure.repositories import cart_repository as repo
from infrastructure.repositories import special_equipment_commerce_repository


@dataclass(frozen=True)
class TransferGuestCartCommand:
    user_id: UUID
    transfer_id: UUID
    vehicle_id: UUID
    quantity: int
    equipments: list[dict[str, Any]]
    services: list[dict[str, Any]]
    allow_overstock: bool = False
    scope: CatalogScope = DEFAULT_CATALOG_SCOPE


@dataclass(frozen=True)
class TransferGuestCartResult:
    transfer_id: UUID
    applied: bool
    cart_item: dict[str, Any] | None


async def handle_transfer_guest_cart(
    cmd: TransferGuestCartCommand,
    session: AsyncSession,
) -> TransferGuestCartResult:
    CartItem.ensure_quantity_valid(cmd.quantity)
    await repo.lock_cart(session, cmd.user_id, cmd.scope)
    expected = {
        "vehicle_id": cmd.vehicle_id, "quantity": cmd.quantity,
        "allow_overstock": cmd.allow_overstock,
        "equipments": cmd.equipments, "services": cmd.services,
    }
    receipt = await repo.get_transfer_receipt(session, cmd.user_id, cmd.scope, cmd.transfer_id)
    if receipt is not None:
        if receipt != expected:
            raise GuestCartTransferConflictError(cmd.transfer_id)
        return TransferGuestCartResult(transfer_id=cmd.transfer_id, applied=False,
            cart_item=await repo.get_cart_item(session, cmd.user_id, cmd.vehicle_id, cmd.scope))
    if not await repo.vehicle_exists(session, cmd.vehicle_id, cmd.scope):
        raise VehicleNotFoundError(cmd.vehicle_id)
    existing = await repo.get_cart_item(session, cmd.user_id, cmd.vehicle_id, cmd.scope)
    quantity = cmd.quantity + (int(existing["quantity"]) if existing else 0)
    allow_overstock = cmd.allow_overstock or bool(existing and existing.get("allow_overstock"))
    product = await special_equipment_commerce_repository.get_product(session, cmd.vehicle_id)
    available_count = 1 if product and product.get("sale_status") == "available" else 0
    CartItem.ensure_stock_quantity(quantity, available=available_count,
                                   allow_overstock=allow_overstock)
    result = await repo.apply_guest_cart_transfer(
        session, user_id=cmd.user_id, scope=cmd.scope, transfer_id=cmd.transfer_id,
        vehicle_id=cmd.vehicle_id, quantity=cmd.quantity, allow_overstock=cmd.allow_overstock,
        equipments=cmd.equipments, services=cmd.services,
    )
    if not result["applied"] and result["receipt"] != expected:
        raise GuestCartTransferConflictError(cmd.transfer_id)

    return TransferGuestCartResult(
        transfer_id=cmd.transfer_id,
        applied=bool(result["applied"]),
        cart_item=result["cart_item"],
    )


__all__ = [
    "TransferGuestCartCommand",
    "TransferGuestCartResult",
    "handle_transfer_guest_cart",
]
