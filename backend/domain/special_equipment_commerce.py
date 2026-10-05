"""Pure business rules for special-equipment commerce."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID

from domain.errors import DomainError
from domain.values import (
    SpecialEquipmentPublicationStatus,
    SpecialEquipmentSaleStatus,
)

MONEY_QUANT = Decimal("0.01")
DEFAULT_PREPAYMENT_PERCENT = Decimal("10.00")
SPECIAL_EQUIPMENT_PUBLICATION_PUBLISHED = (
    SpecialEquipmentPublicationStatus.PUBLISHED.value
)
SPECIAL_EQUIPMENT_PUBLIC_DETAIL_SALE_STATUSES = frozenset(
    {
        SpecialEquipmentSaleStatus.AVAILABLE.value,
        SpecialEquipmentSaleStatus.ON_ORDER.value,
    }
)
SPECIAL_EQUIPMENT_MAX_CART_QUANTITY = 1000


def has_special_equipment_public_detail(
    publication_status: object,
    sale_status: object,
) -> bool:
    """Return whether current product state exposes a public detail page."""

    return (
        publication_status == SPECIAL_EQUIPMENT_PUBLICATION_PUBLISHED
        and sale_status in SPECIAL_EQUIPMENT_PUBLIC_DETAIL_SALE_STATUSES
    )


class SpecialEquipmentCommerceError(DomainError):
    """Base error for the special-equipment bounded context."""


class SpecialEquipmentProductNotFoundError(SpecialEquipmentCommerceError):
    def __init__(self) -> None:
        super().__init__("Единица спецтехники не найдена")


class SpecialEquipmentProductUnavailableError(SpecialEquipmentCommerceError):
    def __init__(self) -> None:
        super().__init__("Единица спецтехники недоступна для выбранной операции")


class SpecialEquipmentPriceRequiredError(SpecialEquipmentCommerceError):
    def __init__(self) -> None:
        super().__init__("Для покупки или предоплаты должна быть задана положительная цена")


class SpecialEquipmentOrderNotFoundError(SpecialEquipmentCommerceError):
    def __init__(self) -> None:
        super().__init__("Заказ спецтехники не найден")


class SpecialEquipmentOrderAccessError(SpecialEquipmentCommerceError):
    def __init__(self) -> None:
        super().__init__("Заказ принадлежит другому пользователю")


class SpecialEquipmentOrderStateError(SpecialEquipmentCommerceError):
    pass


class SpecialEquipmentIdempotencyConflictError(SpecialEquipmentCommerceError):
    def __init__(self) -> None:
        super().__init__("Idempotency-Key уже использован с другим запросом")


class SpecialEquipmentRefundReferenceConflictError(SpecialEquipmentCommerceError):
    def __init__(self) -> None:
        super().__init__(
            "Внешняя ссылка возврата уже подтверждена для другого запроса"
        )


class SpecialEquipmentCartPositionConflictError(SpecialEquipmentCommerceError):
    def __init__(self) -> None:
        super().__init__("Такая позиция уже существует в выбранной группе корзины")


class SpecialEquipmentCartConfigurationConflictError(
    SpecialEquipmentCommerceError
):
    def __init__(self) -> None:
        super().__init__(
            "Одинаковая спецтехника в корзине должна иметь одинаковую цену, "
            "комментарий, комплектацию и услуги"
        )


class SpecialEquipmentPurchaseType(StrEnum):
    RESERVATION = "reservation"
    PREORDER = "preorder"
    FULL_PURCHASE = "full_purchase"
    LEASING = "leasing"


class SpecialEquipmentOrderStatus(StrEnum):
    PAYMENT_PENDING = "payment_pending"
    RESERVED = "reserved"
    PURCHASED = "purchased"
    LEASING_PENDING = "leasing_pending"
    LEASING_ACTIVE = "leasing_active"
    PREORDERED = "preordered"
    CANCELLATION_REQUESTED = "cancellation_requested"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class OrderAmounts:
    total: Decimal
    initial_payment: Decimal
    remaining: Decimal
    down_payment_percent: Decimal | None


@dataclass(frozen=True, slots=True)
class ProductCommerceState:
    id: UUID
    mark_name: str
    model_name: str
    modification_name: str
    manufacture_year: int | None
    vin: str | None
    price: Decimal | None
    currency_code: str
    seller_company_id: UUID | None
    publication_status: str
    sale_status: str
    price_on_request: bool = False
    price_from: Decimal | None = None
    superstructure_id: UUID | None = None
    superstructure_name: str | None = None
    superstructure_type_name: str | None = None
    superstructure_manufacturer: str | None = None
    chassis_mark_name: str | None = None
    chassis_model_name: str | None = None
    chassis_modification_name: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ProductCommerceState:
        raw_price = data.get("price")
        raw_price_from = data.get("price_from")
        super_id = data.get("superstructure_id")
        return cls(
            id=UUID(str(data["id"])),
            mark_name=str(data.get("mark_name") or ""),
            model_name=str(data.get("model_name") or ""),
            modification_name=str(data.get("modification_name") or ""),
            manufacture_year=data.get("manufacture_year"),
            vin=data.get("vin"),
            price=Decimal(str(raw_price)) if raw_price is not None else None,
            price_on_request=bool(data.get("price_on_request", False)),
            price_from=(
                Decimal(str(raw_price_from))
                if raw_price_from is not None
                else None
            ),
            currency_code=str(data.get("currency_code") or "RUB"),
            seller_company_id=(
                UUID(str(data["seller_company_id"]))
                if data.get("seller_company_id")
                else None
            ),
            publication_status=str(data.get("publication_status") or "draft"),
            sale_status=str(data.get("sale_status") or "unavailable"),
            superstructure_id=UUID(str(super_id)) if super_id else None,
            superstructure_name=data.get("superstructure_name"),
            superstructure_type_name=data.get("superstructure_type_name"),
            superstructure_manufacturer=data.get("superstructure_manufacturer"),
            chassis_mark_name=data.get("chassis_mark_name") or (str(data["mark_name"]) if data.get("mark_name") else None),
            chassis_model_name=data.get("chassis_model_name") or (str(data["model_name"]) if data.get("model_name") else None),
            chassis_modification_name=data.get("chassis_modification_name") or (str(data["modification_name"]) if data.get("modification_name") else None),
        )

    def ensure_catalog_action_allowed(self) -> None:
        if self.publication_status != "published":
            raise SpecialEquipmentProductUnavailableError()

    def ensure_commercial_action_allowed(self) -> None:
        self.ensure_catalog_action_allowed()
        if self.sale_status != "available":
            raise SpecialEquipmentProductUnavailableError()

    def ensure_cart_action_allowed(self) -> None:
        self.ensure_catalog_action_allowed()
        if self.sale_status not in {"available", "on_order"}:
            raise SpecialEquipmentProductUnavailableError()

    def ensure_leasing_application_allowed(self) -> None:
        """Allow an orderable offer into an application without reserving it."""

        self.ensure_catalog_action_allowed()
        if self.sale_status not in {"available", "on_order"}:
            raise SpecialEquipmentProductUnavailableError()

    def ensure_purchase_type_allowed(
        self, purchase_type: SpecialEquipmentPurchaseType
    ) -> None:
        self.ensure_catalog_action_allowed()
        if purchase_type == SpecialEquipmentPurchaseType.PREORDER:
            if self.sale_status != "on_order":
                raise SpecialEquipmentProductUnavailableError()
            return
        if self.sale_status != "available":
            raise SpecialEquipmentProductUnavailableError()

    def ensure_group_purchase_type_allowed(
        self,
        purchase_type: SpecialEquipmentPurchaseType,
        *,
        group_has_on_order: bool,
    ) -> None:
        """Validate one physical item inside an atomic cart group.

        A mixed available/on-order bundle is represented by one preorder
        document. The exception applies only when this concrete group really
        contains an on-order line; standalone preorder semantics stay strict.
        """

        if (
            purchase_type == SpecialEquipmentPurchaseType.PREORDER
            and group_has_on_order
        ):
            self.ensure_catalog_action_allowed()
            if self.sale_status not in {"available", "on_order"}:
                raise SpecialEquipmentProductUnavailableError()
            return
        self.ensure_purchase_type_allowed(purchase_type)

    def require_positive_price(self) -> Decimal:
        if self.price_on_request or self.price is None or self.price <= 0:
            raise SpecialEquipmentPriceRequiredError()
        return self.price.quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)

    def snapshot(self) -> dict[str, Any]:
        """Return an immutable, storage-safe order/application snapshot."""

        snapshot_data: dict[str, Any] = {
            "product_id": str(self.id),
            "mark": self.mark_name,
            "model": self.model_name,
            "modification": self.modification_name or None,
            "manufacture_year": self.manufacture_year,
            "vin": self.vin,
            "price": str(self.price) if self.price is not None else None,
            "price_on_request": self.price_on_request,
            "price_from": (
                str(self.price_from) if self.price_from is not None else None
            ),
            "currency_code": self.currency_code,
            "seller_company_id": (
                str(self.seller_company_id) if self.seller_company_id else None
            ),
        }
        if self.superstructure_id is not None:
            from domain.special_equipment_kits import kit_title

            title = kit_title(
                superstructure_name=self.superstructure_name or "",
                chassis_mark_name=self.mark_name,
                chassis_model_name=self.model_name,
            )
            snapshot_data.update(
                {
                    "title": title,
                    "superstructure_name": self.superstructure_name,
                    "superstructure_type_name": self.superstructure_type_name,
                    "superstructure_manufacturer": self.superstructure_manufacturer,
                    "chassis_mark_name": self.mark_name,
                    "chassis_model_name": self.model_name,
                    "chassis_modification_name": self.modification_name or None,
                }
            )
        return snapshot_data


def compute_order_amounts(
    purchase_type: SpecialEquipmentPurchaseType,
    total_price: Decimal,
    down_payment_percent: Decimal | None,
) -> OrderAmounts:
    if total_price <= 0:
        raise SpecialEquipmentPriceRequiredError()
    total = total_price.quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)

    if purchase_type == SpecialEquipmentPurchaseType.FULL_PURCHASE:
        return OrderAmounts(
            total=total,
            initial_payment=total,
            remaining=Decimal("0.00"),
            down_payment_percent=None,
        )
    if purchase_type == SpecialEquipmentPurchaseType.LEASING:
        raise SpecialEquipmentOrderStateError(
            "Лизинговый заказ создаётся только после подтверждения заявки"
        )

    percent = (
        DEFAULT_PREPAYMENT_PERCENT
        if down_payment_percent is None
        else down_payment_percent
    )
    if percent <= 0 or percent >= 100:
        raise SpecialEquipmentOrderStateError(
            "Предоплата должна быть больше 0 и меньше 100 процентов; "
            "для полной оплаты выберите full_purchase"
        )
    initial = (total * percent / Decimal("100")).quantize(
        MONEY_QUANT, rounding=ROUND_HALF_UP
    )
    return OrderAmounts(
        total=total,
        initial_payment=initial,
        remaining=(total - initial).quantize(MONEY_QUANT),
        down_payment_percent=percent.quantize(MONEY_QUANT),
    )


def ensure_order_owned(order_user_id: UUID, actor_user_id: UUID) -> None:
    if order_user_id != actor_user_id:
        raise SpecialEquipmentOrderAccessError()


def ensure_order_can_cancel(status: str) -> None:
    if status not in {
        SpecialEquipmentOrderStatus.PAYMENT_PENDING,
        SpecialEquipmentOrderStatus.RESERVED,
        SpecialEquipmentOrderStatus.PURCHASED,
        SpecialEquipmentOrderStatus.LEASING_PENDING,
        SpecialEquipmentOrderStatus.LEASING_ACTIVE,
        SpecialEquipmentOrderStatus.PREORDERED,
    }:
        raise SpecialEquipmentOrderStateError(
            "Заказ в текущем статусе нельзя отменить"
        )
