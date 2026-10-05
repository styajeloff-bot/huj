"""HTTP contracts for special-equipment commerce resources."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from domain.application_sources import ApplicationCreationSource


class CommerceCapabilities(BaseModel):
    can_favorite: bool
    can_add_to_cart: bool
    can_lease: bool
    can_buy: bool
    can_preorder: bool


class CheckoutConflictResponse(BaseModel):
    """Stable top-level allocation conflict shared by checkout facades."""

    code: str
    message: str
    requested: int | None = None
    available: int | None = None


class CommerceDirectoryRef(BaseModel):
    id: UUID
    name: str


class CommerceImage(BaseModel):
    id: UUID
    content_url: str


class CommerceSuperstructureRef(BaseModel):
    id: UUID
    name: str
    type_name: str | None = None
    manufacturer: str | None = None


class CommerceProductCard(BaseModel):
    id: UUID
    slug: str | None = None
    title: str | None = None
    detail_url: str | None = None
    mark: CommerceDirectoryRef
    model: CommerceDirectoryRef
    modification: CommerceDirectoryRef | None = None
    superstructure: CommerceSuperstructureRef | None = None
    manufacture_year: int | None = None
    body_color: CommerceDirectoryRef | None = None
    price: Decimal | None = None
    base_price: Decimal | None = None
    special_price: Decimal | None = None
    price_on_request: bool = False
    price_from: Decimal | None = None
    currency_code: str
    publication_status: str | None = None
    sale_status: str | None = None
    primary_image: CommerceImage | None = None
    capabilities: CommerceCapabilities


class FavoriteItemOut(BaseModel):
    product_id: UUID
    product: CommerceProductCard
    added_at: datetime


class FavoriteListResponse(BaseModel):
    items: list[FavoriteItemOut]


class FavoritePutResponse(BaseModel):
    created: bool
    product: CommerceProductCard


class PutCartItemRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_id: UUID
    quantity: int = 1
    allow_overstock: bool = False
    parent_item_id: UUID | None = None
    is_selected: bool = True
    comment: str | None = Field(default=None, max_length=2000)
    equipments: list[dict[str, Any]] = Field(default_factory=list)
    services: list[dict[str, Any]] = Field(default_factory=list)


class PatchCartItemRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    quantity: int | None = None
    allow_overstock: bool | None = None
    parent_item_id: UUID | None = None
    is_selected: bool | None = None
    custom_price: Decimal | None = Field(default=None, gt=0)
    comment: str | None = Field(default=None, max_length=2000)
    equipments: list[dict[str, Any]] | None = None
    services: list[dict[str, Any]] | None = None

    @field_validator("quantity", mode="before")
    @classmethod
    def quantity_cannot_be_explicit_null(cls, value: Any) -> Any:
        if value is None:
            raise ValueError("quantity не может быть null")
        return value


class CartItemOut(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: UUID
    product_id: UUID
    quantity: int
    allow_overstock: bool = False
    parent_item_id: UUID | None = None
    transfer_id: UUID | None = None
    is_selected: bool
    custom_price: Decimal | None = None
    comment: str | None = None
    equipments: list[dict[str, Any]] = Field(default_factory=list)
    services: list[dict[str, Any]] = Field(default_factory=list)
    added_at: datetime
    updated_at: datetime
    product: CommerceProductCard


class CartListResponse(BaseModel):
    items: list[CartItemOut]


class CartPutResponse(BaseModel):
    created: bool
    cart_item: CartItemOut


class CartItemPatchOut(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: UUID
    product_id: UUID
    quantity: int
    allow_overstock: bool = False
    parent_item_id: UUID | None = None
    transfer_id: UUID | None = None
    is_selected: bool
    custom_price: Decimal | None = None
    comment: str | None = None
    equipments: list[dict[str, Any]] = Field(default_factory=list)
    services: list[dict[str, Any]] = Field(default_factory=list)
    added_at: datetime
    updated_at: datetime


class CartPatchResponse(BaseModel):
    cart_item: CartItemPatchOut


class GuestCartTransferItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    local_id: UUID
    product_id: UUID
    quantity: int = 1
    allow_overstock: bool = False
    parent_local_id: UUID | None = None
    is_selected: bool = True
    comment: str | None = Field(default=None, max_length=2000)
    equipments: list[dict[str, Any]] = Field(default_factory=list)
    services: list[dict[str, Any]] = Field(default_factory=list)


class GuestCartTransferRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Literal[2]
    items: list[GuestCartTransferItem] = Field(min_length=1, max_length=200)


class GuestCartTransferResponse(BaseModel):
    transfer_id: UUID
    replayed: bool
    item_ids: dict[UUID, UUID]
    items: list[CartItemOut]


class CreateLeasingApplicationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_type: ApplicationCreationSource

    company_id: UUID
    cart_item_ids: list[UUID] = Field(min_length=1, max_length=200)
    comment: str | None = Field(default=None, max_length=2000)
    leasing_purpose: str | None = Field(default=None, max_length=100)
    leasing_purposes: list[Annotated[str, Field(min_length=1, max_length=100)]] | None = None
    regions: list[str] = Field(default_factory=list, max_length=100)
    down_payment_percent: Decimal | None = Field(default=None, gt=0, le=100)
    lease_term_months: int | None = Field(default=None, ge=1, le=120)


class LeasingApplicationCreatedResponse(BaseModel):
    source_type: ApplicationCreationSource | None = None
    application_id: UUID
    display_number: str | None = None
    item_id: UUID
    product_id: UUID
    item_ids: list[UUID] = Field(default_factory=list)
    product_ids: list[UUID] = Field(default_factory=list)
    status: str | None = None
    item_status: str


class CreateOrderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cart_item_ids: list[UUID] = Field(min_length=1, max_length=200)
    purchase_type: Literal["reservation", "preorder", "full_purchase"]
    payment_method: Literal["card", "sbp", "bank_transfer"]
    down_payment_percent: Decimal | None = Field(default=None, gt=0, lt=100)


class CreateRemainingPaymentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    payment_method: Literal["card", "sbp", "bank_transfer"]


class CreateScheduledPaymentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    payment_method: Literal["card", "sbp", "bank_transfer"]


class SpecialEquipmentPaymentOut(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: UUID
    purchase_order_id: UUID
    user_id: UUID
    payment_type: str
    amount: Decimal
    status: str
    payment_method: str | None = None
    error_message: str | None = None
    fiscal_status: str | None = None
    expires_at: datetime | None = None
    paid_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    receipt_content_url: str | None = None


class SpecialEquipmentPaymentWidgetData(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    form_url: str = Field(alias="formUrl")
    form_params: dict[str, str] = Field(alias="formParams")
    order_id: str = Field(alias="orderId")
    amount: Decimal
    expires_at: str = Field(alias="expiresAt")


class SpecialEquipmentPaymentSbpData(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    sbp_link: str = Field(alias="sbpLink")
    order_id: str = Field(alias="orderId")
    amount: Decimal
    description: str
    expires_at: str = Field(alias="expiresAt")


class SpecialEquipmentOrderOut(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: UUID
    user_id: UUID
    product_id: UUID
    seller_company_id: UUID | None = None
    leasing_application_id: UUID | None = None
    purchase_type: str
    status: str
    unit_price: Decimal
    total_price: Decimal
    paid_amount: Decimal
    remaining_amount: Decimal
    currency_code: str
    down_payment_percent: Decimal | None = None
    item_snapshot: dict[str, Any]
    hold_expires_at: datetime | None = None
    cancellation_reason: str | None = None
    cancellation_requested_at: datetime | None = None
    cancelled_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    items: list[SpecialEquipmentOrderItemOut] = Field(default_factory=list)


class SpecialEquipmentOrderItemOut(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: UUID
    purchase_order_id: UUID
    product_id: UUID
    source_cart_item_id: UUID | None = None
    group_id: UUID
    parent_group_id: UUID | None = None
    item_role: str
    position: int
    unit_price: Decimal
    item_snapshot: dict[str, Any]
    created_at: datetime


class CreateOrderResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    order: SpecialEquipmentOrderOut
    payment: SpecialEquipmentPaymentOut | None = None
    replayed: bool
    widget_data: SpecialEquipmentPaymentWidgetData | None = Field(
        default=None,
        alias="widgetData",
    )
    sbp_data: SpecialEquipmentPaymentSbpData | None = Field(
        default=None,
        alias="sbpData",
    )


class CreatePaymentResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    order: SpecialEquipmentOrderOut
    payment: SpecialEquipmentPaymentOut
    replayed: bool
    widget_data: SpecialEquipmentPaymentWidgetData | None = Field(
        default=None,
        alias="widgetData",
    )
    sbp_data: SpecialEquipmentPaymentSbpData | None = Field(
        default=None,
        alias="sbpData",
    )


class SpecialEquipmentLeasingScheduleItemOut(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: UUID
    purchase_order_id: UUID
    payment_number: int
    due_date: date
    amount: Decimal
    principal: Decimal | None = None
    interest: Decimal | None = None
    payment_id: UUID | None = None
    is_paid: bool
    payment_status: str | None = None
    payment_paid_at: datetime | None = None
    receipt_content_url: str | None = None
    can_pay: bool
    created_at: datetime
    updated_at: datetime


class LeasingScheduleResponse(BaseModel):
    items: list[SpecialEquipmentLeasingScheduleItemOut]


class CreateScheduledPaymentResponse(CreatePaymentResponse):
    schedule_item: SpecialEquipmentLeasingScheduleItemOut


class SpecialEquipmentPaymentStatusOut(BaseModel):
    id: UUID
    status: str
    fiscal_status: str | None = None
    receipt_content_url: str | None = None
    error_message: str | None = None
    expires_at: datetime | None = None
    paid_at: datetime | None = None


class SpecialEquipmentPaymentStatusResponse(BaseModel):
    payment: SpecialEquipmentPaymentStatusOut


class OrderListPagination(BaseModel):
    page: int
    page_size: int
    total: int
    pages: int


class OrderListResponse(BaseModel):
    items: list[SpecialEquipmentOrderOut]
    pagination: OrderListPagination


class OrderDetailOut(SpecialEquipmentOrderOut):
    payments: list[SpecialEquipmentPaymentOut] = Field(default_factory=list)


class OrderDetailResponse(BaseModel):
    order: OrderDetailOut


class CancelOrderRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=2000)


class ConfirmOrderRefundRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    external_reference: str = Field(min_length=1, max_length=255)


class OrderMutationResponse(BaseModel):
    order: SpecialEquipmentOrderOut


class RefundConfirmationResponse(BaseModel):
    order: SpecialEquipmentOrderOut
    refunded_amount: Decimal
    refunded_payment_ids: list[UUID]
    replayed: bool


class PaymentConfirmationResponse(BaseModel):
    order: SpecialEquipmentOrderOut
    payment: SpecialEquipmentPaymentOut


class PaymentReconciliationOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    payment_id: UUID | None = None
    purchase_order_id: UUID | None = None
    gateway_transaction_id: str
    status: Literal["manual_review"]
    attempt_count: int
    last_error_code: str | None = None
    manual_review_reason: str
    refund_required: bool
    provider_state: dict[str, Any]
    received_at: datetime
    processed_at: datetime | None = None
    updated_at: datetime


class PaymentReconciliationPagination(BaseModel):
    page: int
    page_size: int
    has_more: bool


class PaymentReconciliationListResponse(BaseModel):
    items: list[PaymentReconciliationOut]
    pagination: PaymentReconciliationPagination


class PaymentReconciliationDetailResponse(BaseModel):
    reconciliation: PaymentReconciliationOut
