"""Pure leasing schedule rules for the special-equipment bounded context."""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

_MONEY = Decimal("0.01")


def _money(value: Decimal) -> Decimal:
    return value.quantize(_MONEY, rounding=ROUND_HALF_UP)


def _add_months(value: date, months: int) -> date:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


@dataclass(frozen=True, slots=True)
class LeasingScheduleEntry:
    payment_number: int
    due_date: date
    amount: Decimal
    principal: Decimal
    interest: Decimal


def _validate_terms(
    *,
    principal_total: Decimal,
    total_cost: Decimal,
    down_payment: Decimal,
    monthly_payment: Decimal,
    lease_term_months: int,
    buyout_amount: Decimal,
) -> None:
    if principal_total <= 0:
        raise ValueError("principal_total must be positive")
    if total_cost < principal_total:
        raise ValueError("total_cost must cover principal_total")
    if lease_term_months < 1:
        raise ValueError("lease_term_months must be positive")
    if monthly_payment <= 0:
        raise ValueError("monthly_payment must be positive")
    if down_payment < 0 or buyout_amount < 0:
        raise ValueError("down_payment and buyout_amount cannot be negative")


def _payment_dates_and_amounts(
    *,
    issued_on: date,
    total_cost: Decimal,
    down_payment: Decimal,
    monthly_payment: Decimal,
    lease_term_months: int,
    buyout_amount: Decimal,
) -> list[tuple[date, Decimal]]:
    values: list[tuple[date, Decimal]] = []
    if down_payment > 0:
        values.append((issued_on, down_payment))
    values.extend(
        (_add_months(issued_on, number), monthly_payment)
        for number in range(1, lease_term_months + 1)
    )
    if buyout_amount > 0:
        values.append((_add_months(issued_on, lease_term_months + 1), buyout_amount))
    last_due, last_amount = values[-1]
    nominal_total = sum((amount for _, amount in values), Decimal("0.00"))
    remainder = total_cost - nominal_total
    maximum_rounding_adjustment = max(
        Decimal("1.00"), Decimal(lease_term_months) * _MONEY
    )
    if abs(remainder) > maximum_rounding_adjustment:
        raise ValueError("accepted proposal total does not match its installments")
    adjusted_last_amount = _money(
        last_amount + remainder
    )
    if adjusted_last_amount <= 0:
        raise ValueError("accepted proposal terms produce a non-positive installment")
    values[-1] = (last_due, adjusted_last_amount)
    return values


def build_leasing_schedule(
    *,
    issued_on: date,
    principal_total: Decimal,
    total_cost: Decimal,
    down_payment: Decimal,
    monthly_payment: Decimal,
    lease_term_months: int,
    buyout_amount: Decimal,
) -> list[LeasingScheduleEntry]:
    """Build a cent-exact schedule from an accepted final proposal.

    The accepted proposal remains the source of truth.  We therefore reject
    irreconcilable terms instead of silently inventing a different payment
    plan.  The final installment absorbs only the normal rounding/remainder
    difference, while principal and interest totals remain exact.
    """

    principal_total = _money(principal_total)
    total_cost = _money(total_cost)
    down_payment = _money(down_payment)
    monthly_payment = _money(monthly_payment)
    buyout_amount = _money(buyout_amount)
    _validate_terms(
        principal_total=principal_total,
        total_cost=total_cost,
        down_payment=down_payment,
        monthly_payment=monthly_payment,
        lease_term_months=lease_term_months,
        buyout_amount=buyout_amount,
    )
    dated_amounts = _payment_dates_and_amounts(
        issued_on=issued_on,
        total_cost=total_cost,
        down_payment=down_payment,
        monthly_payment=monthly_payment,
        lease_term_months=lease_term_months,
        buyout_amount=buyout_amount,
    )

    entries: list[LeasingScheduleEntry] = []
    remaining_principal = principal_total
    for index, (due_date, amount) in enumerate(dated_amounts, start=1):
        is_last = index == len(dated_amounts)
        if is_last:
            principal = remaining_principal
        else:
            principal = min(
                remaining_principal,
                _money(amount * principal_total / total_cost),
            )
        if principal > amount:
            raise ValueError("installment cannot contain negative interest")
        interest = _money(amount - principal)
        entries.append(
            LeasingScheduleEntry(
                payment_number=index,
                due_date=due_date,
                amount=amount,
                principal=principal,
                interest=interest,
            )
        )
        remaining_principal = _money(remaining_principal - principal)

    if remaining_principal != Decimal("0.00"):
        raise ValueError("schedule does not settle principal")
    if sum((row.amount for row in entries), Decimal("0.00")) != total_cost:
        raise ValueError("schedule does not settle total cost")
    return entries
