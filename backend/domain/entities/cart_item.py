"""Shopping-cart item domain entity (dealer / client cart).

Models a single ``shopping_cart`` row keyed by ``(user_id, vehicle_id)``.
Business rules encapsulated here:

* quantity must be ``>= 1`` (``ensure_quantity_valid``),
* a custom price may only be attached by a dealer / employee or by a
  client for a zero-price vehicle (``ensure_custom_price_allowed``),
* rows are user-scoped — every mutation must call ``ensure_owned_by``.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field, fields
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from domain.errors import (
    AccessDeniedError,
    CartCustomPriceDeniedError,
    InsufficientVehiclesError,
    InvalidCartQuantityError,
)

# Roles permitted to override the vehicle price on any cart item.
# Clients may only set a custom price for positions whose underlying vehicle
# has no catalog price yet.
_CUSTOM_PRICE_ROLES: frozenset[str] = frozenset(
    {"dealer", "carcraft_employee"}
)

# Max comment length mirrors the Joi validator in the Express router
# (``updateCommentSchema``) — 500 characters is a soft cap.
COMMENT_MAX_LENGTH = 500


@dataclass
class CartItem:
    """Aggregate root for a single cart position."""

    cart_id: UUID | None = None
    user_id: UUID = field(default_factory=uuid.uuid4)
    vehicle_id: UUID = field(default_factory=uuid.uuid4)
    quantity: int = 1
    is_selected: bool = True
    custom_price: Decimal | None = None
    comment: str | None = None
    added_at: datetime | None = None

    # -------------------------------------------------------------------
    # Hydration
    # -------------------------------------------------------------------

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CartItem:
        """Hydrate from a repository dict, ignoring unknown keys."""
        names = {f.name for f in fields(cls)}
        payload: dict[str, Any] = {
            k: v for k, v in data.items() if k in names
        }
        if "id" in data and "cart_id" not in payload:
            payload["cart_id"] = data["id"]
        custom_price = payload.get("custom_price")
        if custom_price is not None and not isinstance(custom_price, Decimal):
            payload["custom_price"] = Decimal(str(custom_price))
        if "quantity" in payload and payload["quantity"] is None:
            payload["quantity"] = 1
        if "is_selected" in payload and payload["is_selected"] is None:
            payload["is_selected"] = True
        return cls(**payload)

    # -------------------------------------------------------------------
    # Invariants
    # -------------------------------------------------------------------

    def ensure_owned_by(self, user_id: UUID) -> None:
        """Raise AccessDeniedError if ``user_id`` doesn't own this cart item."""
        if self.user_id != user_id:
            raise AccessDeniedError("Нет доступа к данной позиции корзины")

    @staticmethod
    def ensure_quantity_valid(quantity: int) -> None:
        """Raise ``InvalidCartQuantityError`` if ``quantity`` is < 1."""
        if isinstance(quantity, bool) or not isinstance(quantity, int) or not 1 <= quantity <= 2147483647:
            raise InvalidCartQuantityError()

    @staticmethod
    def ensure_stock_quantity(quantity: int, *, available: int, allow_overstock: bool) -> None:
        CartItem.ensure_quantity_valid(quantity)
        if not allow_overstock and quantity > available:
            raise InsufficientVehiclesError(requested=quantity, available=available)

    @staticmethod
    def ensure_custom_price_allowed_for_role(role: str | None) -> None:
        """Raise ``CartCustomPriceDeniedError`` unless the role is dealer/employee."""
        if role not in _CUSTOM_PRICE_ROLES:
            raise CartCustomPriceDeniedError()

    @staticmethod
    def ensure_custom_price_allowed(
        role: str | None,
        base_price: Decimal | None,
        *,
        vehicle_exists: bool = True,
    ) -> None:
        """Allow clients to price only cart items with no stored vehicle price."""
        if role in _CUSTOM_PRICE_ROLES:
            return
        if role == "client" and vehicle_exists and (
            base_price is None or Decimal(str(base_price)) <= Decimal("0")
        ):
            return
        raise CartCustomPriceDeniedError()
