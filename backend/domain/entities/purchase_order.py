"""PurchaseOrder aggregate root — business rules for orders."""
import uuid
from dataclasses import dataclass, field, fields
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any
from uuid import UUID

from domain.errors import (
    AccessDeniedError,
    InvalidOrderStatusError,
)
from domain.values import OrderStatus, PurchaseType, VehicleStatus


@dataclass
class PurchaseOrder:
    """Aggregate root. Encapsulates order invariants and status machine."""

    id: UUID = field(default_factory=uuid.uuid4)
    user_id: UUID = field(default_factory=uuid.uuid4)
    vehicle_id: UUID = field(default_factory=uuid.uuid4)
    purchase_type: str = ""
    status: str = ""
    total_price: Decimal = Decimal(0)
    paid_amount: Decimal = Decimal(0)
    remaining_amount: Decimal = Decimal(0)
    leasing_application_id: uuid.UUID | None = None
    cancellation_reason: str | None = None
    cancellation_requested_at: datetime | None = None
    cancelled_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    # ------------------------------------------------------------------
    # Factory helpers
    # ------------------------------------------------------------------

    @staticmethod
    def compute_amounts(
        purchase_type: str,
        total_price: Decimal | float,
        use_gateway: bool,
        down_payment_percent: float | None = None,
    ) -> tuple[Decimal, Decimal, Decimal, str, str]:
        """Return (payment_amount, initial_paid, initial_remaining, order_status, payment_type)."""
        total = Decimal(str(total_price))
        if purchase_type == PurchaseType.RESERVATION:
            pct = Decimal(str(10 if down_payment_percent is None else down_payment_percent)) / Decimal("100")
            payment_amount = (total * pct).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            remaining = (total - payment_amount).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            order_status = OrderStatus.RESERVED
            payment_type = "reservation"
        else:
            payment_amount = total
            remaining = Decimal("0.00")
            order_status = OrderStatus.PURCHASED
            payment_type = "full_purchase"

        initial_paid = Decimal("0.00") if use_gateway else payment_amount
        initial_remaining = total if use_gateway else remaining
        return payment_amount, initial_paid, initial_remaining, order_status, payment_type

    # ------------------------------------------------------------------
    # Ownership
    # ------------------------------------------------------------------

    def ensure_owned_by(self, user_id: UUID) -> None:
        if self.user_id != user_id:
            raise AccessDeniedError()

    # ------------------------------------------------------------------
    # Status guards
    # ------------------------------------------------------------------

    def ensure_can_pay_remaining(self) -> Decimal:
        """Assert remaining payment is allowed, return amount to pay."""
        if self.status != OrderStatus.RESERVED:
            raise InvalidOrderStatusError(
                "Доплата доступна только для зарезервированных автомобилей"
            )
        amount = self.remaining_amount
        if amount <= Decimal("0.00"):
            raise InvalidOrderStatusError("Нет остатка к оплате")
        return amount

    def ensure_can_request_cancellation(self) -> None:
        if self.status not in (OrderStatus.RESERVED, OrderStatus.PURCHASED):
            raise InvalidOrderStatusError(
                "Отмена невозможна для данного статуса заказа"
            )

    def ensure_can_approve_cancellation(self) -> None:
        if self.status != OrderStatus.CANCELLATION_REQUESTED:
            raise InvalidOrderStatusError(
                "Заказ не находится в статусе запроса на отмену"
            )

    def ensure_can_pay_schedule(self) -> None:
        if self.status != OrderStatus.LEASING_ACTIVE:
            raise InvalidOrderStatusError(
                "Оплата доступна только для активного лизинга"
            )

    def ensure_has_schedule(self) -> None:
        if self.status not in (OrderStatus.LEASING_ACTIVE, OrderStatus.LEASING_PENDING):
            raise InvalidOrderStatusError(
                "График платежей доступен только для заказов в лизинге"
            )

    # ------------------------------------------------------------------
    # Vehicle status mapping
    # ------------------------------------------------------------------

    @staticmethod
    def target_vehicle_status(purchase_type: str) -> str:
        """Vehicle status to set after creating an order."""
        return VehicleStatus.RESERVED if purchase_type == PurchaseType.RESERVATION else VehicleStatus.SOLD

    # ------------------------------------------------------------------
    # Conversion
    # ------------------------------------------------------------------

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PurchaseOrder":
        """Hydrate entity from a repository dict (ignores extra keys)."""
        names = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in names})
