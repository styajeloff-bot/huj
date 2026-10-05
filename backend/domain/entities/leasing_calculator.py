"""LeasingCalculator domain entity.

Pure business logic for the leasing calculator. Mirrors the Express
``CalculatorService`` math (annuity-based monthly payment, VAT refund, profit
tax savings) and the support-program application rules.

The entity carries no I/O — handlers pull rates / vehicles / support-programs
from repositories and feed them in here as plain data.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from domain.errors import InvalidCalculationParamsError

# ---------------------------------------------------------------------------
# Support types — string constants (no enum to keep coupling low; values
# come back from the DB as plain strings).
# ---------------------------------------------------------------------------

SUPPORT_TYPE_VEHICLE_DISCOUNT = frozenset({
    "vehicle_discount_dealer_compensation",
    "vehicle_discount_dealer_invoice",
})
SUPPORT_TYPE_DEALER_COMMISSION = "vehicle_discount_dealer_invoice"
SUPPORT_TYPE_DOWN_PAYMENT = "down_payment_compensation"
SUPPORT_TYPE_INTEREST = "leasing_interest_compensation"

# Validation thresholds — copied from the Express Joi schema.
MIN_LEASE_TERM_MONTHS = 12
MAX_LEASE_TERM_MONTHS = 84
MAX_DOWN_PAYMENT_PERCENT = 49.0
MAX_BUYOUT_PERCENT = 5.0
MAX_TOTAL_AMOUNT = 10_000_000_000.0


@dataclass(frozen=True)
class LeasingRates:
    """Rates used by the calculator. Hydrated from `leasing_rates` table."""

    key_rate: float
    surcharge: float
    vat_rate: float
    profit_tax_rate: float


@dataclass(frozen=True)
class LeasingCalculationResult:
    """Plain data structure for one leasing calculation."""

    monthly_payment: int
    monthly_principal_payment: int
    monthly_interest_payment: int
    total_cost: int
    total_interest: int
    markup: int
    markup_percent: float
    rate: float
    buyout_amount: int
    vat_refund: int
    profit_tax_savings: int
    total_savings: int

    def to_camel_dict(self) -> dict[str, Any]:
        """Express-compatible camelCase dict for response and history save."""
        return {
            "monthlyPayment": self.monthly_payment,
            "monthlyPrincipalPayment": self.monthly_principal_payment,
            "monthlyInterestPayment": self.monthly_interest_payment,
            "totalCost": self.total_cost,
            "totalInterest": self.total_interest,
            "markup": self.markup,
            "markupPercent": self.markup_percent,
            "rate": self.rate,
            "buyoutAmount": self.buyout_amount,
            "vatRefund": self.vat_refund,
            "profitTaxSavings": self.profit_tax_savings,
            "totalSavings": self.total_savings,
        }


@dataclass(frozen=True)
class SupportPaymentAmounts:
    """Amounts after applying support without changing the chosen advance base."""

    base_total: int
    effective_total: int
    contract_down_payment: int
    client_down_payment: int
    client_down_payment_percent: float


@dataclass
class CalculationParams:
    """Validated calculator input."""

    total_amount: float
    down_payment: float
    down_payment_percent: float
    lease_term_months: int
    buyout_amount: float = 0.0
    buyout_percent: float | None = None
    vehicle_ids: list[UUID] = field(default_factory=list)
    vehicle_price_overrides: dict[UUID, float] = field(default_factory=dict)
    vehicle_quantities: dict[UUID, int] = field(default_factory=dict)
    selected_support: dict[Any, list[Any]] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Aggregate root
# ---------------------------------------------------------------------------


class LeasingCalculator:
    """Calculator domain logic — only static methods, kept stateless."""

    # ---- Core math ----------------------------------------------------

    @staticmethod
    def compute_dynamic_rate(rates: LeasingRates) -> float:
        """Total rate applied to the principal."""
        return rates.key_rate + rates.surcharge

    @staticmethod
    def compute_monthly_payment(
        principal: float, monthly_rate: float, term_months: int
    ) -> float:
        """Annuity formula. Falls back to even principal split when rate is 0."""
        if principal <= 0 or term_months <= 0:
            return 0.0
        if monthly_rate > 0:
            compound = (1 + monthly_rate) ** term_months
            annuity_factor = (monthly_rate * compound) / (compound - 1)
        else:
            annuity_factor = 1.0 / term_months
        return principal * annuity_factor

    @staticmethod
    def compute_vat_refund(total_cost: float, vat_rate: float) -> float:
        """VAT slice extracted from a VAT-inclusive total."""
        if total_cost <= 0 or vat_rate <= 0:
            return 0.0
        return total_cost * vat_rate / (100 + vat_rate)

    @staticmethod
    def compute_profit_tax_savings(
        total_cost: float, profit_tax_rate: float
    ) -> float:
        """Saving on profit tax that the lessee can claim."""
        if total_cost <= 0 or profit_tax_rate <= 0:
            return 0.0
        return total_cost * profit_tax_rate / (100 + profit_tax_rate)

    @staticmethod
    def compute_total_savings(vat_refund: float, profit_tax_savings: float) -> float:
        return max(0.0, vat_refund) + max(0.0, profit_tax_savings)

    @staticmethod
    def compute_leasing(
        total_amount: float,
        down_payment: float,
        term_months: int,
        rates: LeasingRates,
        buyout_amount: float = 0.0,
    ) -> LeasingCalculationResult:
        """Full calculation for one (sub)contract. Mirrors Express output."""
        if total_amount <= 0:
            return LeasingCalculationResult(
                monthly_payment=0,
                monthly_principal_payment=0,
                monthly_interest_payment=0,
                total_cost=round(down_payment + buyout_amount),
                total_interest=0,
                markup=0,
                markup_percent=0.0,
                rate=0.0,
                buyout_amount=round(buyout_amount),
                vat_refund=0,
                profit_tax_savings=0,
                total_savings=0,
            )

        rate = LeasingCalculator.compute_dynamic_rate(rates)
        monthly_rate = rate / 100 / 12
        principal = total_amount - down_payment

        if principal > 0:
            monthly_payment = LeasingCalculator.compute_monthly_payment(
                principal, monthly_rate, term_months
            )
            total_cost = monthly_payment * term_months + down_payment + buyout_amount
            total_interest = total_cost - total_amount - down_payment
        else:
            monthly_payment = 0.0
            total_cost = down_payment + buyout_amount
            total_interest = 0.0

        markup_percent = (
            (total_interest / total_amount) * 100 if total_amount > 0 else 0.0
        )
        vat_refund = LeasingCalculator.compute_vat_refund(total_cost, rates.vat_rate)
        profit_tax = LeasingCalculator.compute_profit_tax_savings(
            total_cost, rates.profit_tax_rate
        )
        savings = LeasingCalculator.compute_total_savings(vat_refund, profit_tax)

        return LeasingCalculationResult(
            monthly_payment=round(monthly_payment),
            monthly_principal_payment=round(monthly_payment * 0.7),
            monthly_interest_payment=round(monthly_payment * 0.3),
            total_cost=round(total_cost),
            total_interest=round(total_interest),
            markup=round(total_interest),
            markup_percent=round(markup_percent * 100) / 100,
            rate=round(rate * 100) / 100,
            buyout_amount=round(buyout_amount),
            vat_refund=round(vat_refund),
            profit_tax_savings=round(profit_tax),
            total_savings=round(savings),
        )

    # ---- Validation ---------------------------------------------------

    @staticmethod
    def validate_params(params: CalculationParams) -> None:
        if params.total_amount < 0 or params.total_amount > MAX_TOTAL_AMOUNT:
            raise InvalidCalculationParamsError(
                "Сумма должна быть в диапазоне 0..10000000000"
            )
        if params.down_payment < 0:
            raise InvalidCalculationParamsError("Аванс не может быть отрицательным")
        if not (0 <= params.down_payment_percent <= MAX_DOWN_PAYMENT_PERCENT):
            raise InvalidCalculationParamsError(
                "Процент аванса должен быть в диапазоне 0..49"
            )
        if not (
            MIN_LEASE_TERM_MONTHS
            <= params.lease_term_months
            <= MAX_LEASE_TERM_MONTHS
        ):
            raise InvalidCalculationParamsError(
                "Срок лизинга должен быть от 12 до 84 месяцев"
            )
        if params.buyout_amount < 0:
            raise InvalidCalculationParamsError(
                "Выкупная стоимость не может быть отрицательной"
            )
        if params.buyout_percent is not None and not (
            0 <= params.buyout_percent <= MAX_BUYOUT_PERCENT
        ):
            raise InvalidCalculationParamsError(
                "Процент выкупа должен быть в диапазоне 0..5"
            )

    @staticmethod
    def ensure_total_amount_within_limits(total_amount: float) -> None:
        if total_amount < 0 or total_amount > MAX_TOTAL_AMOUNT:
            raise InvalidCalculationParamsError(
                "Сумма должна быть в диапазоне 0..10000000000"
            )

    @staticmethod
    def ensure_advance_within_total(
        contract_down_payment: float, effective_total: float
    ) -> None:
        if contract_down_payment > effective_total:
            raise InvalidCalculationParamsError(
                "Аванс не может превышать стоимость автомобилей"
            )

    @staticmethod
    def ensure_buyout_within_principal(
        buyout_amount: float, effective_total: float, contract_down_payment: float
    ) -> None:
        if buyout_amount > (effective_total - contract_down_payment):
            raise InvalidCalculationParamsError(
                "Выкупная стоимость не может превышать сумму лизинга"
            )

    # ---- Support program math -----------------------------------------

    @staticmethod
    def compute_support_payment_amounts(
        *,
        base_total: float,
        down_payment_percent: float,
        vehicle_discount_support: float = 0.0,
        down_payment_support: float = 0.0,
        interest_support: float = 0.0,
    ) -> SupportPaymentAmounts:
        """Apply support while keeping the contract advance on the base total."""

        normalized_base = max(0.0, base_total)
        effective_total = max(
            0.0,
            normalized_base - max(0.0, vehicle_discount_support),
        )
        contract_down_payment = round(
            normalized_base * (down_payment_percent / 100)
        )
        client_down_payment = max(
            0,
            contract_down_payment
            - round(max(0.0, down_payment_support))
            - round(max(0.0, interest_support)),
        )
        client_percent = (
            round((client_down_payment / effective_total) * 10_000) / 100
            if effective_total > 0
            else down_payment_percent
        )
        return SupportPaymentAmounts(
            base_total=round(normalized_base),
            effective_total=round(effective_total),
            contract_down_payment=contract_down_payment,
            client_down_payment=client_down_payment,
            client_down_payment_percent=client_percent,
        )

    @staticmethod
    def compute_support_from_params(
        params: dict[str, Any] | None, base_amount: float
    ) -> int:
        """Compute one support-program contribution given its `support_params` JSON.

        Mirrors `computeSupportFromParams` in CalculatorService.js — percent vs
        fixed amount with min/max clamps, finally clamped to the base.
        """
        if not params or not isinstance(params, dict) or base_amount <= 0:
            return 0
        try:
            value = float(params.get("value", 0) or 0)
        except (TypeError, ValueError):
            return 0
        if value <= 0:
            return 0
        value_type = "percent" if params.get("value_type") == "percent" else "amount"
        if value_type == "percent":
            support: float = round((base_amount * value) / 100)
            min_amount = (
                float(params["min_amount"]) if params.get("min_amount") is not None else None
            )
            max_amount = (
                float(params["max_amount"]) if params.get("max_amount") is not None else None
            )
            if min_amount is not None and support < min_amount:
                support = min_amount
            if max_amount is not None and support > max_amount:
                support = max_amount
        else:
            support = value
            min_pct = (
                float(params["min_percent"]) if params.get("min_percent") is not None else None
            )
            max_pct = (
                float(params["max_percent"]) if params.get("max_percent") is not None else None
            )
            floor = (
                round((base_amount * min_pct) / 100) if min_pct is not None else None
            )
            cap = (
                round((base_amount * max_pct) / 100) if max_pct is not None else None
            )
            if floor is not None and support < floor:
                support = floor
            if cap is not None and support > cap:
                support = cap
        support = min(support, base_amount)
        return max(0, round(support))
