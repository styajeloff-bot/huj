"""Pydantic schemas for the exchange subsystem API (Phase 5 E2)."""
from __future__ import annotations

import datetime as _dt
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


class MessageResponse(BaseModel):
    message: str


# ---------------------------------------------------------------------------
# Exchange requests
# ---------------------------------------------------------------------------


class ExchangeRequestWarehouseIn(BaseModel):
    model_config = ConfigDict(extra="ignore")

    warehouse_id: UUID
    dealer_id: UUID
    dealer_comment: str | None = None


class CreateExchangeRequestBody(BaseModel):
    model_config = ConfigDict(extra="ignore")

    product_id: UUID | None = None
    vehicle_id: UUID | None = None
    quantity: int = Field(default=1, ge=1)
    discount_type: str | None = None
    discount_value: Decimal | None = None
    file_url: str | None = None
    file_name: str | None = None
    expiration_at: AwareDatetime | None = None
    dealer_option_ids: list[UUID] = Field(default_factory=list)
    warehouses: list[ExchangeRequestWarehouseIn] = Field(default_factory=list)
    selected_support_ids: list[UUID] = Field(default_factory=list)

    @model_validator(mode="after")
    def _ensure_product_id(self) -> CreateExchangeRequestBody:
        if self.product_id is None and self.vehicle_id is not None:
            self.product_id = self.vehicle_id
        if self.product_id is None:
            raise ValueError("product_id is required")
        return self


class UpdateExchangeRequestBody(BaseModel):
    model_config = ConfigDict(extra="ignore")

    quantity: int | None = Field(default=None, ge=1)
    discount_type: str | None = None
    discount_value: Decimal | None = None
    expiration_at: AwareDatetime | None = None
    file_url: str | None = None
    file_name: str | None = None


class PatchExchangeRequestBody(BaseModel):
    """Partial update with optional status dispatch.

    - `{"status": "archived"}` — archive this request (equivalent to the
      former `PUT /exchange/requests/:id/archive`).
    - `{"status": "open"}` — duplicate an archived / deal request as a new
      one (equivalent to the former `POST /exchange/requests/:id/resubmit`).
    Omitting `status` updates the basic fields of the current request.
    """

    model_config = ConfigDict(extra="ignore")

    status: str | None = None
    quantity: int | None = Field(default=None, ge=1)
    discount_type: str | None = None
    discount_value: Decimal | None = None
    expiration_at: AwareDatetime | None = None
    file_url: str | None = None
    file_name: str | None = None


class ExchangeRequestOut(BaseModel):
    id: UUID
    lc_user_id: UUID
    lc_company_id: UUID | None = None
    product_id: UUID
    quantity: int
    expiration_at: AwareDatetime | None = None
    discount_type: str | None = None
    discount_value: Decimal | None = None
    file_url: str | None = None
    file_name: str | None = None
    status: str
    accepted_bid_id: UUID | None = None
    selected_support_ids: list[UUID] = Field(default_factory=list)
    support_program_details: list[dict[str, Any]] = Field(default_factory=list)
    support_price_base: int = 0
    support_price_display: int = 0
    support_price_amount: int = 0
    batch_number: int | None = None
    batch_index: int | None = None
    created_at: _dt.datetime | None = None
    updated_at: _dt.datetime | None = None


class ExchangeRequestCreatedResponse(BaseModel):
    message: str
    request: ExchangeRequestOut
    batch_number: int | None = None


class ExchangeRequestUpdatedResponse(BaseModel):
    message: str
    request: ExchangeRequestOut


class ExchangeRequestPagination(BaseModel):
    page: int
    limit: int
    total: int
    pages: int


class ExchangeRequestListResponse(BaseModel):
    requests: list[ExchangeRequestOut]
    pagination: ExchangeRequestPagination


class DistributorExchangeRequestListResponse(BaseModel):
    items: list[ExchangeRequestOut]
    pagination: ExchangeRequestPagination


class ExchangeRequestCountsResponse(BaseModel):
    counts: dict[str, int]


class ExchangeRequestDetailResponse(BaseModel):
    request: dict[str, Any]
    warehouses: list[dict[str, Any]]
    options: list[dict[str, Any]]
    dealer_comments: list[dict[str, Any]]
    files: list[dict[str, Any]]
    bids: list[dict[str, Any]]


# ---------------------------------------------------------------------------
# Bids
# ---------------------------------------------------------------------------


class CreateBidBody(BaseModel):
    model_config = ConfigDict(extra="ignore")

    request_id: UUID
    price: Decimal = Field(gt=Decimal("0"))
    quantity: int = Field(default=1, ge=1)
    comment: str | None = None
    dealer_option_ids: list[UUID] = Field(default_factory=list)


class UpdateBidBody(BaseModel):
    model_config = ConfigDict(extra="ignore")

    price: Decimal | None = Field(default=None, gt=Decimal("0"))
    quantity: int | None = Field(default=None, ge=1)
    comment: str | None = None
    dealer_option_ids: list[UUID] | None = None


class RespondToKpBody(BaseModel):
    model_config = ConfigDict(extra="ignore")

    action: str = Field(pattern="^(accepted|rejected)$")
    comment: str | None = None


class AddBidCommentBody(BaseModel):
    model_config = ConfigDict(extra="ignore")

    comment: str = Field(min_length=1)


class ExchangeBidOut(BaseModel):
    id: UUID
    request_id: UUID
    dealer_id: UUID | None
    price: Decimal
    quantity: int
    comment: str | None = None
    is_accepted: bool = False
    kp_file_url: str | None = None
    kp_file_name: str | None = None
    kp_status: str | None = "none"
    kp_dealer_comment: str | None = None
    kp_sent_at: _dt.datetime | None = None
    kp_responded_at: _dt.datetime | None = None
    bid_file_url: str | None = None
    bid_file_name: str | None = None
    created_at: _dt.datetime | None = None
    updated_at: _dt.datetime | None = None


class ExchangeBidCreatedResponse(BaseModel):
    message: str
    bid: ExchangeBidOut


class ExchangeBidListResponse(BaseModel):
    bids: list[ExchangeBidOut]


class ExchangeBidDetailResponse(BaseModel):
    bid: dict[str, Any]
    options: list[dict[str, Any]]
    comments: list[dict[str, Any]]


class ExchangeBidApproveResponse(BaseModel):
    message: str
    bid: ExchangeBidOut


class ExchangeBidFileResponse(BaseModel):
    message: str
    bid: ExchangeBidOut


class AddBidCommentResponse(BaseModel):
    message: str
    comment: dict[str, Any]


# ---------------------------------------------------------------------------
# Cart
# ---------------------------------------------------------------------------


class AddToExchangeCartBody(BaseModel):
    model_config = ConfigDict(extra="ignore")

    product_id: UUID
    quantity: int = Field(default=1, ge=1)
    # Pre-selects the warehouse the user clicked "add to cart" from, so
    # the cart dropdown shows the right checkbox toggled by default.
    warehouse_id: UUID | None = Field(default=None)
    selected_support_ids: list[UUID] | None = None


class CartItemDealerCommentPatch(BaseModel):
    dealer_id: UUID
    comment: str | None = None


class UpdateExchangeCartItemBody(BaseModel):
    model_config = ConfigDict(extra="ignore")

    quantity: int | None = Field(default=None, ge=1)
    discount_type: str | None = None
    discount_value: Decimal | None = None
    expiration_at: AwareDatetime | None = None
    # Server-side persistence of the dealer-selection UI.
    # Every field is optional — only the keys the client actually sends
    # get applied (a missing key does not wipe existing rows).
    warehouses: list[UUID] | None = None
    options: list[UUID] | None = None
    dealer_comment: CartItemDealerCommentPatch | None = None
    selected_support_ids: list[UUID] | None = None


class ExchangeCartCountResponse(BaseModel):
    count: int


class ExchangeCartItemOut(BaseModel):
    id: UUID
    user_id: UUID
    product_id: UUID
    quantity: int
    expiration_at: AwareDatetime | None = None
    discount_type: str | None = None
    discount_value: Decimal | None = None
    file_url: str | None = None
    file_name: str | None = None
    selected_support_ids: list[UUID] = Field(default_factory=list)
    support_price_base: int = 0
    support_price_display: int = 0
    support_price_amount: int = 0
    created_at: _dt.datetime | None = None
    updated_at: _dt.datetime | None = None


class ExchangeCartAddResponse(BaseModel):
    message: str
    item: ExchangeCartItemOut
    created: bool


class ExchangeCartUpdateResponse(BaseModel):
    message: str
    item: ExchangeCartItemOut


class ExchangeCartListResponse(BaseModel):
    cart_items: list[dict[str, Any]]
    summary: dict[str, Any]


class ExchangeCartClearedResponse(BaseModel):
    message: str
    deleted_count: int


class ExchangeCartSubmitResponse(BaseModel):
    message: str
    request_ids: list[UUID]
    count: int
    batch_number: int | None = None
