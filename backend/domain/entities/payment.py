"""Payment entity — creation helpers and lifecycle rules."""
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from domain.errors import (
    ScheduleItemAlreadyPaidError,
    ScheduleItemMismatchError,
    ScheduleItemNotFoundError,
)
from domain.values import PaymentMethod, PaymentStatus

PAYMENT_EXPIRY_MINUTES = 30


class Payment:
    """Static helpers for payment creation logic (no mutable state needed)."""

    @staticmethod
    def uses_gateway(payment_method: str | None) -> bool:
        return bool(payment_method and payment_method != PaymentMethod.BANK_TRANSFER)

    @staticmethod
    def initial_status(use_gateway: bool) -> str:
        return PaymentStatus.PENDING if use_gateway else PaymentStatus.PROCESSING

    @staticmethod
    def compute_expiry(use_gateway: bool) -> datetime | None:
        if use_gateway:
            return datetime.now(UTC) + timedelta(minutes=PAYMENT_EXPIRY_MINUTES)
        return None


def validate_schedule_item[T: Mapping[str, Any]](item: T | None, order_id: UUID) -> T:
    """Enforce schedule-item invariants before payment. Returns the validated item."""
    if not item:
        raise ScheduleItemNotFoundError()
    if item["purchase_order_id"] != order_id:
        raise ScheduleItemMismatchError()
    if item["is_paid"]:
        raise ScheduleItemAlreadyPaidError()
    return item
