"""Leasing terms of a deal, computed with the calculator's formulas in ``Decimal``.

Annuity payment on ``total - down_payment`` at ``key_rate + surcharge`` per year; the
contract cost is ``down_payment + monthly_payment * term + buyout``. The existing
float calculator is not reused: the process requires exact kopeck arithmetic.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, localcontext
from typing import Any

from domain.fast_deals.errors import FastDealValidationError
from domain.fast_deals.money import (
    CENT,
    HUNDRED,
    ZERO,
    money,
    nonnegative_money,
    percent,
    positive_money,
)
from domain.fast_deals.values import (
    MAX_DOWN_PAYMENT_PERCENT,
    MAX_LEASE_TERM_MONTHS,
    MIN_LEASE_TERM_MONTHS,
    DownPaymentMode,
)


def validate_term(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise FastDealValidationError("Срок лизинга — целое число месяцев", field="lease_term_months")
    if not MIN_LEASE_TERM_MONTHS <= value <= MAX_LEASE_TERM_MONTHS:
        raise FastDealValidationError(
            f"Срок лизинга — от {MIN_LEASE_TERM_MONTHS} до {MAX_LEASE_TERM_MONTHS} месяцев",
            field="lease_term_months",
        )
    return value


def annuity_payment(
    principal: Decimal, annual_rate_percent: Decimal, term_months: int
) -> Decimal:
    """Monthly annuity; an even split when the rate is zero."""
    if principal <= 0 or term_months <= 0:
        return ZERO
    monthly_rate = annual_rate_percent / HUNDRED / Decimal(12)
    with localcontext() as ctx:
        ctx.prec = 50
        if monthly_rate > 0:
            compound = (Decimal(1) + monthly_rate) ** term_months
            factor = monthly_rate * compound / (compound - Decimal(1))
        else:
            factor = Decimal(1) / Decimal(term_months)
        return money(principal * factor)


@dataclass(frozen=True)
class DownPayment:
    """The advance in the single active input mode."""

    mode: DownPaymentMode
    amount: Decimal
    percent: Decimal


def resolve_down_payment(
    total: Decimal, *, amount: Any = None, percent_value: Any = None
) -> DownPayment:
    """Exactly one of rubles / percent; the other side is derived from it."""
    if (amount is None) == (percent_value is None):
        raise FastDealValidationError(
            "Укажите аванс либо в рублях, либо в процентах", field="down_payment"
        )
    if percent_value is not None:
        pct = percent(percent_value, field="down_payment_percent")
        if pct > MAX_DOWN_PAYMENT_PERCENT:
            raise FastDealValidationError(
                f"Аванс не может быть больше {MAX_DOWN_PAYMENT_PERCENT}%",
                field="down_payment_percent",
            )
        rubles = money(total * pct / HUNDRED)
        return DownPayment(DownPaymentMode.PERCENT, rubles, pct)
    rubles = nonnegative_money(amount, field="down_payment")
    if rubles > total:
        raise FastDealValidationError(
            "Аванс не может превышать стоимость техники", field="down_payment"
        )
    pct = (
        ZERO
        if total <= 0
        else (rubles * HUNDRED / total).quantize(CENT, rounding=ROUND_HALF_UP)
    )
    if pct > MAX_DOWN_PAYMENT_PERCENT:
        raise FastDealValidationError(
            f"Аванс не может быть больше {MAX_DOWN_PAYMENT_PERCENT}%", field="down_payment"
        )
    return DownPayment(DownPaymentMode.AMOUNT, rubles, pct)


@dataclass(frozen=True)
class LeasingTerms:
    """Complete, internally consistent terms for one total."""

    total: Decimal
    down_payment_mode: DownPaymentMode
    down_payment: Decimal
    down_payment_percent: Decimal
    lease_term_months: int
    monthly_payment: Decimal
    monthly_payment_is_manual: bool
    calculated_monthly_payment: Decimal
    buyout_amount: Decimal
    total_cost: Decimal

    def columns(self) -> dict[str, Any]:
        """Persistent requested-terms columns of ``fast_deals``."""
        return {
            "down_payment_mode": self.down_payment_mode.value,
            "down_payment": self.down_payment,
            "down_payment_percent": self.down_payment_percent,
            "lease_term_months": self.lease_term_months,
            "monthly_payment": self.monthly_payment,
            "monthly_payment_is_manual": self.monthly_payment_is_manual,
            "calculated_monthly_payment": self.calculated_monthly_payment,
            "buyout_amount": self.buyout_amount,
            "calc_snapshot": self.snapshot(),
        }

    def snapshot(self) -> dict[str, str]:
        """Terms only: never contains supports, so it is safe for any projection."""
        return {
            "total": format(self.total, "f"),
            "financed_amount": format(self.total - self.down_payment, "f"),
            "down_payment": format(self.down_payment, "f"),
            "down_payment_percent": format(self.down_payment_percent, "f"),
            "lease_term_months": str(self.lease_term_months),
            "monthly_payment": format(self.monthly_payment, "f"),
            "calculated_monthly_payment": format(self.calculated_monthly_payment, "f"),
            "buyout_amount": format(self.buyout_amount, "f"),
            "total_cost": format(self.total_cost, "f"),
        }


def contract_cost(
    down_payment: Decimal, monthly_payment: Decimal, term_months: int, buyout: Decimal
) -> Decimal:
    return money(down_payment + monthly_payment * term_months + buyout)


def validate_buyout(buyout: Any, total: Decimal, down_payment: Decimal) -> Decimal:
    value = nonnegative_money(buyout if buyout is not None else 0, field="buyout_amount")
    if value > total - down_payment:
        raise FastDealValidationError(
            "Выкупной платёж не может превышать сумму лизинга", field="buyout_amount"
        )
    return value


def build_terms(
    total: Decimal,
    *,
    down: DownPayment,
    lease_term_months: int,
    buyout: Any,
    annual_rate_percent: Decimal | None,
    manual_monthly_payment: Any = None,
) -> LeasingTerms:
    """Terms from the user's inputs.

    A manual payment is kept as entered while the recomputed one is stored beside
    it. Without rates and without a manual payment the payment cannot be known.
    """
    term = validate_term(lease_term_months)
    buyout_amount = validate_buyout(buyout, total, down.amount)
    calculated = (
        annuity_payment(total - down.amount, annual_rate_percent, term)
        if annual_rate_percent is not None
        else None
    )
    if manual_monthly_payment is not None:
        monthly = nonnegative_money(manual_monthly_payment, field="monthly_payment")
        is_manual = True
        if calculated is None:
            calculated = monthly
    else:
        if calculated is None:
            raise FastDealValidationError(
                "Ставки калькулятора не настроены: введите ежемесячный платёж вручную",
                field="monthly_payment",
            )
        monthly = calculated
        is_manual = False
    return LeasingTerms(
        total=total,
        down_payment_mode=down.mode,
        down_payment=down.amount,
        down_payment_percent=down.percent,
        lease_term_months=term,
        monthly_payment=monthly,
        monthly_payment_is_manual=is_manual,
        calculated_monthly_payment=calculated,
        buyout_amount=buyout_amount,
        total_cost=contract_cost(down.amount, monthly, term, buyout_amount),
    )


def rebase_terms(
    deal: dict[str, Any], new_total: Decimal, annual_rate_percent: Decimal | None
) -> LeasingTerms | None:
    """Apply a changed vehicle total to existing terms.

    The input mode is kept (percent → rubles follow, rubles → percent follows). A
    manual monthly payment survives the change; the recomputed one is shown beside
    it. Returns ``None`` while the terms are not complete yet.
    """
    term = deal.get("lease_term_months")
    mode = deal.get("down_payment_mode")
    if term is None or mode is None:
        return None
    if mode == DownPaymentMode.PERCENT:
        down = resolve_down_payment(new_total, percent_value=deal["down_payment_percent"])
    else:
        rubles = deal["down_payment"]
        if rubles > new_total:
            raise FastDealValidationError(
                "Аванс превышает новую стоимость техники: измените аванс", field="down_payment"
            )
        down = resolve_down_payment(new_total, amount=rubles)
    buyout = deal.get("buyout_amount") or ZERO
    if buyout > new_total - down.amount:
        raise FastDealValidationError(
            "Выкупной платёж превышает сумму лизинга: измените выкуп", field="buyout_amount"
        )
    manual = deal["monthly_payment"] if deal.get("monthly_payment_is_manual") else None
    return build_terms(
        new_total,
        down=down,
        lease_term_months=term,
        buyout=buyout,
        annual_rate_percent=annual_rate_percent,
        manual_monthly_payment=manual,
    )


def split_terms(
    deal: dict[str, Any],
    part_total: Decimal,
    original_total: Decimal,
    annual_rate_percent: Decimal | None,
) -> LeasingTerms | None:
    """Terms of one dealer's part after the DL split.

    The term and the advance percent are copied. The advance in rubles, the payment,
    the buyout and the contract cost are computed again for the part's total by the
    current formula; the original monthly sum is neither divided nor kept as manual.
    """
    term = deal.get("lease_term_months")
    pct = deal.get("down_payment_percent")
    if term is None or pct is None:
        return None
    down = resolve_down_payment(part_total, percent_value=pct)
    original_buyout = deal.get("buyout_amount") or ZERO
    if original_total > 0:
        buyout = money(original_buyout * part_total / original_total)
    else:
        buyout = ZERO
    buyout = min(buyout, max(part_total - down.amount, ZERO))
    return build_terms(
        part_total,
        down=down,
        lease_term_months=term,
        buyout=buyout,
        annual_rate_percent=annual_rate_percent,
    )


def require_complete_terms(deal: dict[str, Any]) -> None:
    """Terms needed to send the deal."""
    for field, message in (
        ("lease_term_months", "Укажите срок лизинга"),
        ("down_payment", "Укажите аванс"),
        ("monthly_payment", "Укажите ежемесячный платёж"),
    ):
        if deal.get(field) is None:
            raise FastDealValidationError(message, field=field)


def validate_offer_amounts(
    *,
    total_amount: Any,
    down_payment: Any,
    lease_term_months: Any,
    monthly_payment: Any,
    total_cost: Any,
    buyout_amount: Any = None,
) -> dict[str, Decimal | int]:
    """Mandatory financial fields of an offer (КП)."""
    amount = positive_money(total_amount, field="total_amount")
    down = nonnegative_money(down_payment, field="down_payment")
    if down > amount:
        raise FastDealValidationError("Аванс не может превышать сумму финансирования", field="down_payment")
    return {
        "total_amount": amount,
        "down_payment": down,
        "lease_term_months": validate_term(lease_term_months),
        "monthly_payment": nonnegative_money(monthly_payment, field="monthly_payment"),
        "total_cost": positive_money(total_cost, field="total_cost"),
        "buyout_amount": nonnegative_money(
            buyout_amount if buyout_amount is not None else 0, field="buyout_amount"
        ),
    }
