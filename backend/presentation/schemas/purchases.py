"""Pydantic schemas for purchases API (request + response)."""
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Input schemas
# ---------------------------------------------------------------------------

class PurchaseItem(BaseModel):
    product_id: UUID
    quantity: int = Field(default=1, ge=1, le=100)


class CreatePurchaseRequest(BaseModel):
    items: list[PurchaseItem] = Field(min_length=1)
    purchase_type: Literal["reservation", "full_purchase"]
    payment_method: Literal["card", "sbp", "bank_transfer"] | None = None
    down_payment_percent: float | None = Field(default=None, ge=1, le=100)


class CreatePaymentRequest(BaseModel):
    """Body for POST /purchases/{order_id}/payments.

    `scope` = `remaining` — оплата оставшейся суммы.
    `scope` = `scheduled` — оплата конкретного взноса по графику лизинга
    (`schedule_id` обязателен).
    """

    scope: Literal["remaining", "scheduled"]
    schedule_id: UUID | None = None
    payment_method: Literal["card", "sbp", "bank_transfer"] | None = None


class RequestCancellationRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=1000)


# ---------------------------------------------------------------------------
# Base entity schemas
# ---------------------------------------------------------------------------

class PurchaseOrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    product_id: UUID
    purchase_type: str
    status: str
    total_price: Decimal
    paid_amount: Decimal
    remaining_amount: Decimal
    leasing_application_id: uuid.UUID | None = None
    cancellation_reason: str | None = None
    cancellation_requested_at: datetime | None = None
    cancelled_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class PurchaseOrderSummaryOut(PurchaseOrderOut):
    """Заказ с кратким описанием автомобиля (список заказов)."""

    vin: str | None = None
    color: str | None = None
    vehicle_year: int | None = None
    images: list[Any] | None = None
    vehicle_status: str | None = None
    mark_name: str | None = None
    mark_cyrillic: str | None = None
    model_name: str | None = None
    model_cyrillic: str | None = None
    generation_name: str | None = None
    configuration_name: str | None = None
    modification_name: str | None = None
    warehouse_name: str | None = None
    warehouse_address: str | None = None
    warehouse_brand: str | None = None
    base_price: Decimal | None = None
    discount_price: Decimal | None = None


class PurchaseOrderDetailOut(PurchaseOrderOut):
    """Заказ с полными данными автомобиля (детали заказа)."""

    vin: str | None = None
    color: str | None = None
    vehicle_year: int | None = None
    images: list[Any] | None = None
    vehicle_status: str | None = None
    vehicle_base_price: Decimal | None = None
    vehicle_discount_price: Decimal | None = None
    mark_name: str | None = None
    mark_cyrillic: str | None = None
    model_name: str | None = None
    model_cyrillic: str | None = None
    generation_name: str | None = None
    configuration_name: str | None = None
    modification_name: str | None = None
    warehouse_name: str | None = None
    warehouse_address: str | None = None
    warehouse_brand: str | None = None


class PurchaseOrderWithPaymentOut(PurchaseOrderOut):
    """Заказ с id созданного платежа (возвращается после создания)."""

    payment_id: UUID | None = None


class PaymentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    purchase_order_id: UUID
    user_id: UUID
    payment_type: str
    amount: Decimal
    status: str
    gateway_transaction_id: str | None = None
    gateway_response: dict[str, Any] | None = None
    receipt_url: str | None = None
    receipt_s3_key: str | None = None
    error_message: str | None = None
    paid_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    payment_method: str | None = None
    fiscal_status: str | None = None
    fiscal_receipt_id: str | None = None
    fiscal_response: dict[str, Any] | None = None
    fiscal_retry_count: int | None = None
    fiscal_error_message: str | None = None
    expires_at: datetime | None = None


class ScheduleItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    purchase_order_id: UUID
    payment_number: int
    due_date: date
    amount: Decimal
    principal: Decimal
    interest: Decimal
    payment_id: UUID | None = None
    is_paid: bool
    created_at: datetime
    payment_status: str | None = None
    payment_paid_at: datetime | None = None
    receipt_url: str | None = None


class ActiveVehicleOut(BaseModel):
    product_id: UUID
    status: str
    purchase_type: str


# ---------------------------------------------------------------------------
# Receipt / status
# ---------------------------------------------------------------------------

class ReceiptOrderSummary(BaseModel):
    id: UUID
    total_price: Decimal
    mark_name: str | None = None
    model_name: str | None = None
    vin: str | None = None
    vehicle_year: int | None = None


class PaymentReceiptOut(BaseModel):
    payment: PaymentOut
    order: ReceiptOrderSummary


class PaymentWidgetData(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    form_url: str = Field(alias="formUrl")
    # The signed bag of strings as computed by the payment gateway — must be
    # POSTed to ModulBank verbatim. Typing as a strict model here would force
    # re-validation and drop/reshape fields away from what was signed.
    form_params: dict[str, str] = Field(alias="formParams")
    order_id: UUID = Field(alias="orderId")
    amount: float
    expires_at: str = Field(alias="expiresAt")


class PaymentSbpData(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    sbp_link: str = Field(alias="sbpLink")
    order_id: UUID = Field(alias="orderId")
    amount: float
    description: str
    expires_at: str = Field(alias="expiresAt")


class PaymentStatusOut(BaseModel):
    id: UUID
    status: str
    fiscal_status: str | None = None
    receipt_url: str | None = None
    error_message: str | None = None
    paid_at: datetime | None = None


# ---------------------------------------------------------------------------
# Endpoint response wrappers
# ---------------------------------------------------------------------------

class OrdersListResponse(BaseModel):
    orders: list[PurchaseOrderSummaryOut]


class OrderDetailResponse(BaseModel):
    order: PurchaseOrderDetailOut


class VehiclesResponse(BaseModel):
    vehicles: list[ActiveVehicleOut]


class PaymentsListResponse(BaseModel):
    payments: list[PaymentOut]


class ScheduleListResponse(BaseModel):
    schedule: list[ScheduleItemOut]


class ReceiptResponse(BaseModel):
    receipt: PaymentReceiptOut


class PaymentStatusResponse(BaseModel):
    payment: PaymentStatusOut | None = None


class OrderResponse(BaseModel):
    order: PurchaseOrderOut


class CreatePurchaseResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    orders: list[PurchaseOrderWithPaymentOut]
    widget_data: PaymentWidgetData | None = Field(default=None, alias="widgetData")
    sbp_data: PaymentSbpData | None = Field(default=None, alias="sbpData")


class CreatePaymentResponse(BaseModel):
    """Unified response for POST /purchases/{order_id}/payments.

    `order` присутствует только для `scope=remaining`.
    `scheduleItem` присутствует только для `scope=scheduled`.
    `widgetData`/`sbpData` присутствует только при gateway-оплате (card/sbp).
    """

    model_config = ConfigDict(populate_by_name=True)

    payment: PaymentOut
    order: PurchaseOrderOut | None = None
    schedule_item: ScheduleItemOut | None = Field(default=None, alias="scheduleItem")
    widget_data: PaymentWidgetData | None = Field(default=None, alias="widgetData")
    sbp_data: PaymentSbpData | None = Field(default=None, alias="sbpData")
