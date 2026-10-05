"""Position price: catalog base, one adjustment, accounted support and options.

``final_price = base_price - discount + markup - accounted_support
               + equipments_total + services_total``
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from decimal import Decimal
from typing import Any

from domain.fast_deals.errors import FastDealValidationError
from domain.fast_deals.money import ZERO, money, nonnegative_money, positive_money
from domain.fast_deals.values import AdjustmentType


def base_price_for_catalog_unit(
    *,
    price: Decimal | None,
    special_price: Decimal | None,
    price_on_request: bool,
    explicit_price: Any = None,
) -> Decimal:
    """``special_price`` if set, else ``price``.

    A request-priced listing never borrows ``price_from``: the user states the
    agreed price explicitly.
    """
    if price_on_request:
        if explicit_price is None:
            raise FastDealValidationError(
                "Для объявления «цена по запросу» укажите согласованную цену",
                field="price",
            )
        return positive_money(explicit_price, field="price")
    base = special_price if special_price is not None else price
    if base is None:
        raise FastDealValidationError("У объявления не указана цена", field="price")
    return positive_money(base, field="price")


def manual_base_price(value: Any) -> Decimal:
    """A manual position always carries an explicitly stated price."""
    if value is None:
        raise FastDealValidationError("Укажите цену", field="price")
    return positive_money(value, field="price")


def validate_adjustment(
    adjustment_type: str | None, amount: Any, *, allowed: Iterable[AdjustmentType]
) -> tuple[AdjustmentType | None, Decimal | None]:
    """Discount and markup are mutually exclusive; ``None`` clears the adjustment."""
    if adjustment_type is None and amount is None:
        return None, None
    if adjustment_type is None or amount is None:
        raise FastDealValidationError(
            "Укажите тип и размер корректировки цены", field="adjustment"
        )
    try:
        kind = AdjustmentType(adjustment_type)
    except ValueError as exc:
        raise FastDealValidationError("Неизвестный тип корректировки", field="type") from exc
    if kind not in set(allowed):
        raise FastDealValidationError(
            "Этот тип корректировки недоступен в данной сделке", field="type"
        )
    return kind, positive_money(amount, field="amount")


def options_total(items: Iterable[Mapping[str, Any]]) -> Decimal:
    total = ZERO
    for item in items:
        total += nonnegative_money(item.get("price", 0), field="price")
    return money(total)


def compute_final_price(
    *,
    base_price: Decimal,
    adjustment_type: str | None,
    adjustment_amount: Decimal | None,
    support_amount: Decimal,
    equipments_total: Decimal,
    services_total: Decimal,
) -> tuple[Decimal, Decimal]:
    """Return ``(final_price, effective_support)``.

    Support never takes the price below zero: only the part that fits is accounted.
    """
    discount = ZERO
    markup = ZERO
    if adjustment_type == AdjustmentType.DISCOUNT and adjustment_amount is not None:
        discount = adjustment_amount
    elif adjustment_type == AdjustmentType.MARKUP and adjustment_amount is not None:
        markup = adjustment_amount
    gross = base_price - discount + markup + equipments_total + services_total
    if gross < 0:
        raise FastDealValidationError(
            "Итоговая цена не может быть отрицательной", field="price"
        )
    effective_support = min(max(support_amount, ZERO), gross)
    return money(gross - effective_support), money(effective_support)
