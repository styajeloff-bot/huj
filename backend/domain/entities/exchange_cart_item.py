"""ExchangeCartItem — simple aggregate for an LC's exchange-cart line.

This is the LC-side cart where items accumulate before being submitted as
``ExchangeRequest`` rows (``submitCart`` in Express). Each cart item ties
a vehicle, optional warehouses (see `exchange_cart_item_warehouses`),
options (`exchange_cart_item_options`) and per-dealer comments
(`exchange_cart_item_dealer_comments`).
"""
from __future__ import annotations

from dataclasses import dataclass, field, fields
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from domain.errors import (
    ExchangeCartItemNotFoundError,
    InvalidCartQuantityError,
)


def _to_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (ValueError, ArithmeticError, TypeError):
        return None


def _to_int(value: Any, default: int = 0) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


@dataclass
class ExchangeCartItem:
    """A single vehicle line in an LC user's exchange cart."""

    id: UUID = field(default_factory=uuid4)
    user_id: UUID = field(default_factory=uuid4)
    vehicle_id: UUID = field(default_factory=uuid4)
    quantity: int = 1
    discount_type: str | None = None
    discount_value: Decimal | None = None
    file_url: str | None = None
    file_name: str | None = None
    expiration_at: Any | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ExchangeCartItem:
        names = {f.name for f in fields(cls)}
        cleaned: dict[str, Any] = {}
        for key, raw in data.items():
            if key not in names:
                continue
            if key == "discount_value":
                cleaned[key] = _to_decimal(raw)
            elif key == "quantity":
                cleaned[key] = _to_int(raw, default=1)
            elif key in {"id", "user_id", "vehicle_id"}:
                cleaned[key] = raw if isinstance(raw, UUID) else UUID(str(raw)) if raw else UUID(int=0)
            else:
                cleaned[key] = raw
        return cls(**cleaned)

    def ensure_owned_by(self, user_id: UUID) -> None:
        if self.user_id != user_id:
            # Ownership is enforced via repo's (id, user_id) filter; treat
            # mismatch as not-found to avoid leaking row existence.
            raise ExchangeCartItemNotFoundError(self.id)

    def ensure_quantity_valid(self) -> None:
        if self.quantity < 1:
            raise InvalidCartQuantityError()
