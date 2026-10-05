"""HTTP schemas for /api/v1/cart/*.

Pydantic models here are strictly for OpenAPI documentation — FastAPI
does not validate ``JSONResponse`` bodies against ``response_model``.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# Comment length cap mirrors Joi in express/features/cart/cart.routes.js.
COMMENT_MAX_LENGTH = 500


# ---------------------------------------------------------------------------
# Cart item / list
# ---------------------------------------------------------------------------


class CartItemOut(BaseModel):
    """A cart row joined with its vehicle's base fields."""

    cart_id: UUID
    user_id: UUID | None = None
    product_id: UUID
    quantity: int
    allow_overstock: bool = False
    is_selected: bool
    custom_price: Decimal | None = None
    comment: str | None = None
    equipments: list[dict[str, Any]] = Field(default_factory=list)
    services: list[dict[str, Any]] = Field(default_factory=list)
    added_at: datetime | None = None

    # vehicle snapshot
    base_price: Decimal | None = None
    discount_price: Decimal | None = None
    mark_id: str | None = None
    mark_name: str | None = None
    model_id: str | None = None
    model_name: str | None = None
    complectation_id: str | None = None
    configuration_id: str | None = None
    configuration_name: str | None = None
    group_name: str | None = None
    color: str | None = None
    color_inter: str | None = None
    year: int | None = None
    vin: str | None = None
    images: dict[str, Any] | list[Any] | None = None
    status: str | None = None
    is_available: bool | None = None


class CartListResponse(BaseModel):
    items: list[CartItemOut]


# ---------------------------------------------------------------------------
# Count projection (``GET /cart?fields=count``)
# ---------------------------------------------------------------------------


class CartCountResponse(BaseModel):
    count: int


# ---------------------------------------------------------------------------
# Requests
# ---------------------------------------------------------------------------


class AddToCartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_id: UUID
    quantity: int = Field(default=1, ge=1, le=2147483647)
    allow_overstock: bool = False


class AddToCartResultItem(BaseModel):
    cart_id: UUID
    user_id: UUID | None = None
    product_id: UUID
    quantity: int
    allow_overstock: bool = False
    is_selected: bool
    added_at: datetime | None = None


class AddToCartResponse(BaseModel):
    message: str
    cart_item: AddToCartResultItem
    created: bool


class GuestCartTransferRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_id: UUID
    quantity: int = Field(default=1, ge=1, le=2147483647)
    allow_overstock: bool = False
    equipments: list[CartEquipmentOption] = Field(default_factory=list)
    services: list[CartServiceOption] = Field(default_factory=list)


class GuestCartTransferItem(AddToCartResultItem):
    equipments: list[dict[str, Any]] = Field(default_factory=list)
    services: list[dict[str, Any]] = Field(default_factory=list)


class GuestCartTransferResponse(BaseModel):
    transfer_id: UUID
    applied: bool
    cart_item: GuestCartTransferItem | None


class PatchCartItemRequest(BaseModel):
    """Partial update body for ``PATCH /cart/{product_id}``.

    Any subset of fields may be provided. Omitted fields keep their
    current values. Passing ``comment = null`` or an empty string clears
    the comment; passing ``custom_price = null`` clears the custom price.
    """

    model_config = ConfigDict(extra="forbid")

    is_selected: bool | None = None
    quantity: int | None = Field(default=None, ge=1, le=2147483647)
    allow_overstock: bool | None = None
    custom_price: Decimal | None = Field(default=None, ge=0)
    comment: str | None = Field(default=None, max_length=COMMENT_MAX_LENGTH)
    equipments: list[CartEquipmentOption] | None = None
    services: list[CartServiceOption] | None = None


class CartEquipmentOption(BaseModel):
    model_config = ConfigDict(extra="ignore")

    equipment_code: str = Field(min_length=1, max_length=64)
    price: Decimal = Field(default=Decimal("0"), ge=0)


class CartServiceOption(BaseModel):
    model_config = ConfigDict(extra="ignore")

    service_code: str = Field(min_length=1, max_length=64)
    price: Decimal = Field(default=Decimal("0"), ge=0)


class UpdateCartItemResponse(BaseModel):
    message: str
    cart_item: dict[str, Any]


class BulkUpdateCartItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_id: UUID
    is_selected: bool


class BulkUpdateCartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[BulkUpdateCartItem] = Field(min_length=1)


class BulkUpdatedCartItemOut(BaseModel):
    cart_id: UUID
    product_id: UUID
    is_selected: bool


class BulkUpdateCartResponse(BaseModel):
    message: str
    updated_items: list[BulkUpdatedCartItemOut]


class RemoveFromCartResponse(BaseModel):
    message: str
    removed: bool


class ClearCartResponse(BaseModel):
    message: str
    deleted_count: int
