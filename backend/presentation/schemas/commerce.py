"""Public contracts for the unified vehicle/special-equipment commerce API."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from domain.application_sources import ApplicationCreationSource
from presentation.schemas.applications import (
    DraftCalculationPayload,
    DraftCompanyInfoRequest,
)


class VehicleItemRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["vehicle"]
    id: UUID


class SpecialEquipmentItemRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["special_equipment"]
    id: UUID


CommerceItemRef = Annotated[
    VehicleItemRef | SpecialEquipmentItemRef,
    Field(discriminator="type"),
]


class VehicleOrderRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["vehicle"]
    id: UUID


class SpecialEquipmentOrderRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["special_equipment"]
    id: UUID


CommerceOrderRef = Annotated[
    VehicleOrderRef | SpecialEquipmentOrderRef,
    Field(discriminator="type"),
]


class CommerceCapabilities(BaseModel):
    can_lease: bool
    can_buy: bool
    can_preorder: bool


class CommerceFact(BaseModel):
    label: str
    value: str


class CommerceItem(BaseModel):
    ref: CommerceItemRef
    title: str
    subtitle: str | None = None
    image_url: str | None = None
    detail_url: str | None = None
    price: Decimal | None = None
    price_on_request: bool = False
    price_from: Decimal | None = None
    currency_code: str
    availability: str
    manufacturer: str | None = None
    model: str | None = None
    modification: str | None = None
    year: int | None = None
    facts: list[CommerceFact] = Field(default_factory=list)
    capabilities: CommerceCapabilities


class CommerceItemResponse(BaseModel):
    item: CommerceItem


class CommerceItemSnapshot(BaseModel):
    title: str
    subtitle: str | None = None
    image_url: str | None = None
    manufacturer: str | None = None
    model: str | None = None
    modification: str | None = None
    year: int | None = None


class CommerceOrder(BaseModel):
    id: UUID
    item: CommerceItemRef
    item_snapshot: CommerceItemSnapshot
    purchase_type: str
    status: str
    total_price: Decimal
    paid_amount: Decimal
    remaining_amount: Decimal
    currency_code: str
    leasing_application_id: UUID | None = None
    down_payment_percent: Decimal | None = None
    hold_expires_at: datetime | None = None
    cancellation_reason: str | None = None
    cancellation_requested_at: datetime | None = None
    cancelled_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class CommercePayment(BaseModel):
    id: UUID
    order: CommerceOrderRef
    payment_type: str
    amount: Decimal
    status: str
    payment_method: str | None = None
    error_message: str | None = None
    fiscal_status: str | None = None
    expires_at: datetime | None = None
    paid_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    receipt_content_url: str | None = None


class CommerceScheduleItem(BaseModel):
    id: UUID
    order: CommerceOrderRef
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
    created_at: datetime | None = None
    updated_at: datetime | None = None


class CommerceWidgetData(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    form_url: str = Field(alias="formUrl")
    form_params: dict[str, str] = Field(alias="formParams")
    order_id: str = Field(alias="orderId")
    amount: Decimal
    expires_at: str = Field(alias="expiresAt")


class CommerceSbpData(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    sbp_link: str = Field(alias="sbpLink")
    order_id: str = Field(alias="orderId")
    amount: Decimal
    description: str
    expires_at: str = Field(alias="expiresAt")


class CreateCommerceOrderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item: CommerceItemRef
    quantity: int = Field(default=1, ge=1, le=100)
    purchase_type: Literal["reservation", "preorder", "full_purchase"]
    payment_method: Literal["card", "sbp", "bank_transfer"]
    down_payment_percent: Decimal | None = Field(default=None, gt=0, lt=100)
    cart_item_ids: list[UUID] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def validate_quantity(self) -> CreateCommerceOrderRequest:
        if self.item.type == "vehicle" and self.quantity != 1:
            raise ValueError(
                "Пакетное оформление временно недоступно; оформляйте каждую "
                "единицу отдельным заказом"
            )
        if self.item.type == "vehicle" and self.payment_method == "bank_transfer":
            raise ValueError(
                "Безналичный перевод для автомобиля временно недоступен; "
                "выберите оплату картой или СБП"
            )
        if self.item.type == "vehicle" and self.purchase_type == "preorder":
            raise ValueError("Предзаказ доступен только для спецтехники под заказ")
        if self.item.type == "vehicle" and self.cart_item_ids:
            raise ValueError("cart_item_ids доступны только для спецтехники")
        if len(self.cart_item_ids) != len(set(self.cart_item_ids)):
            raise ValueError("Позиции серверной корзины не должны повторяться")
        if (
            self.purchase_type == "full_purchase"
            and self.down_payment_percent is not None
        ):
            raise ValueError(
                "down_payment_percent допустим только для reservation или preorder"
            )
        return self


class CreateCommerceOrderResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    orders: list[CommerceOrder] = Field(min_length=1)
    payments: list[CommercePayment]
    replayed: bool
    widget_data: CommerceWidgetData | None = Field(default=None, alias="widgetData")
    sbp_data: CommerceSbpData | None = Field(default=None, alias="sbpData")


class CommerceOrderListResponse(BaseModel):
    items: list[CommerceOrder]


class CommerceOrderResponse(BaseModel):
    order: CommerceOrder


class CommercePaymentListResponse(BaseModel):
    items: list[CommercePayment]


class CreateCommercePaymentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scope: Literal["remaining", "scheduled"]
    schedule_id: UUID | None = None
    payment_method: Literal["card", "sbp", "bank_transfer"]

    @model_validator(mode="after")
    def validate_schedule(self) -> CreateCommercePaymentRequest:
        if self.scope == "scheduled" and self.schedule_id is None:
            raise ValueError("schedule_id обязателен для scheduled-платежа")
        if self.scope == "remaining" and self.schedule_id is not None:
            raise ValueError("schedule_id допустим только для scheduled-платежа")
        return self


class CreateCommercePaymentResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    order: CommerceOrder
    payment: CommercePayment
    schedule_item: CommerceScheduleItem | None = None
    replayed: bool
    widget_data: CommerceWidgetData | None = Field(default=None, alias="widgetData")
    sbp_data: CommerceSbpData | None = Field(default=None, alias="sbpData")


class CommercePaymentResponse(BaseModel):
    payment: CommercePayment


class CommerceScheduleResponse(BaseModel):
    items: list[CommerceScheduleItem]


class CancelCommerceOrderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str | None = Field(default=None, max_length=2000)


class CommerceLeasingApplicationItemRequest(BaseModel):
    """One typed line in a unified leasing application request."""

    model_config = ConfigDict(extra="forbid")

    item: CommerceItemRef
    quantity: int = Field(default=1, ge=1, le=2147483647)
    allow_overstock: bool = False
    custom_price: Decimal | None = Field(default=None, gt=0)
    comment: str | None = Field(default=None, max_length=2000)
    equipments: list[dict[str, Any]] = Field(default_factory=list, max_length=100)
    services: list[dict[str, Any]] = Field(default_factory=list, max_length=100)
    leasing_purpose: str | None = Field(default=None, max_length=100)
    leasing_purposes: list[Annotated[str, Field(min_length=1, max_length=100)]] | None = None
    leasing_purpose_comment: str | None = Field(default=None, max_length=100)
    regions: list[str] = Field(default_factory=list, max_length=100)
    cart_item_ids: list[UUID] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def validate_quantity(self) -> CommerceLeasingApplicationItemRequest:
        if self.item.type != "vehicle" and (self.quantity > 100 or self.allow_overstock):
            raise ValueError("Для спецтехники сохраняется ограничение количества и наличия")
        if self.item.type == "vehicle" and self.cart_item_ids:
            raise ValueError("cart_item_ids доступны только для спецтехники")
        if len(self.cart_item_ids) != len(set(self.cart_item_ids)):
            raise ValueError("Позиции серверной корзины не должны повторяться")
        for option in [*self.equipments, *self.services]:
            raw_price = option.get("price")
            if raw_price is None:
                continue
            try:
                price = Decimal(str(raw_price))
            except (ArithmeticError, TypeError, ValueError) as exc:
                raise ValueError("Некорректная стоимость дополнительной опции") from exc
            if not price.is_finite() or price < 0:
                raise ValueError(
                    "Стоимость дополнительной опции не может быть отрицательной"
                )
        return self


class CommerceLeasingCalculationRequest(DraftCalculationPayload):
    """Strict flat calculator snapshot persisted with a mixed application."""

    model_config = ConfigDict(extra="forbid")


class CreateCommerceLeasingApplicationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_type: ApplicationCreationSource

    items: list[CommerceLeasingApplicationItemRequest] = Field(
        min_length=1,
        max_length=100,
    )
    company_id: UUID | None = None
    company: DraftCompanyInfoRequest | None = None
    name: str = Field(default="", max_length=255)
    email: str = Field(default="", max_length=255)
    down_payment_percent: Decimal | None = Field(default=None, ge=0, le=49)
    lease_term_months: int | None = Field(default=None, ge=12, le=84)
    calculation: CommerceLeasingCalculationRequest | None = None

    @model_validator(mode="after")
    def validate_company(self) -> CreateCommerceLeasingApplicationRequest:
        if self.company_id is None and self.company is None:
            raise ValueError("Необходимо указать company_id или company")
        refs = [(line.item.type, line.item.id) for line in self.items]
        if len(refs) != len(set(refs)):
            raise ValueError("Одна позиция не может повторяться в заявке")
        return self


class CreatedCommerceLeasingApplicationItem(BaseModel):
    item: CommerceItemRef
    line_id: UUID
    quantity: int = Field(ge=1)


class CreateCommerceLeasingApplicationResponse(BaseModel):
    source_type: ApplicationCreationSource | None = None
    application_id: UUID
    display_number: str | None = None
    items: list[CreatedCommerceLeasingApplicationItem] = Field(min_length=1)
    status: str
