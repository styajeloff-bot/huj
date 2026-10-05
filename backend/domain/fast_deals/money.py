"""Exact money arithmetic: ``Decimal`` only, kopeck precision, half-up rounding."""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from domain.fast_deals.errors import FastDealValidationError

CENT = Decimal("0.01")
ZERO = Decimal("0.00")
HUNDRED = Decimal(100)
# numeric(15, 2): thirteen integer digits.
MAX_MONEY = Decimal("9999999999999.99")


def to_decimal(value: Any, *, field: str | None = None) -> Decimal:
    """Accept ``Decimal``, ``int`` or ``str``; binary floats are refused."""
    if isinstance(value, bool | float):
        raise FastDealValidationError("Сумма должна быть точным числом", field=field)
    if isinstance(value, Decimal):
        result = value
    else:
        try:
            result = Decimal(str(value).strip().replace(",", "."))
        except (InvalidOperation, ValueError) as exc:
            raise FastDealValidationError("Некорректная сумма", field=field) from exc
    if not result.is_finite():
        raise FastDealValidationError("Некорректная сумма", field=field)
    return result


def money(value: Any, *, field: str | None = None) -> Decimal:
    """Quantize to kopecks, rejecting values that do not fit ``numeric(15, 2)``."""
    result = to_decimal(value, field=field).quantize(CENT, rounding=ROUND_HALF_UP)
    if abs(result) > MAX_MONEY:
        raise FastDealValidationError("Сумма слишком велика", field=field)
    return result


def nonnegative_money(value: Any, *, field: str | None = None) -> Decimal:
    result = money(value, field=field)
    if result < 0:
        raise FastDealValidationError("Сумма не может быть отрицательной", field=field)
    return result


def positive_money(value: Any, *, field: str | None = None) -> Decimal:
    result = money(value, field=field)
    if result <= 0:
        raise FastDealValidationError("Сумма должна быть больше нуля", field=field)
    return result


def percent(value: Any, *, field: str | None = None) -> Decimal:
    """Percent with the scale of ``numeric(5, 2)``."""
    result = to_decimal(value, field=field).quantize(CENT, rounding=ROUND_HALF_UP)
    if result < 0 or result > HUNDRED:
        raise FastDealValidationError("Процент должен быть от 0 до 100", field=field)
    return result


def wire(value: Decimal | None) -> str | None:
    """Exact decimal string for the API, kopeck precision."""
    if value is None:
        return None
    return format(value.quantize(CENT, rounding=ROUND_HALF_UP), "f")
