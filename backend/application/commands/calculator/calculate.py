"""Calculate leasing — command + handler.

Mirrors `CalculatorService.calculate` from Express. Hydrates rates / vehicles /
support programs through the calculator repository, applies support-program
math via the LeasingCalculator domain entity, and (if a user is provided)
saves a row into ``calculation_history``.

The shape of the response keeps Express's camelCase keys for the
``calculation`` block (frontend backwards compatibility) while wrapper keys
remain snake_case to match the rest of the FastAPI surface.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.support_programs import build_applicable_support_programs
from domain.entities.cart_item import CartItem
from domain.entities.leasing_calculator import (
    SUPPORT_TYPE_DEALER_COMMISSION,
    SUPPORT_TYPE_DOWN_PAYMENT,
    SUPPORT_TYPE_INTEREST,
    SUPPORT_TYPE_VEHICLE_DISCOUNT,
    CalculationParams,
    LeasingCalculationResult,
    LeasingCalculator,
    LeasingRates,
)
from domain.entities.support_program import are_support_programs_pairwise_compatible
from domain.errors import InvalidCalculationParamsError, LeasingRatesNotConfiguredError
from infrastructure.repositories import calculator_repository as repo
from infrastructure.repositories import support_repository
from infrastructure.settings import settings

logger = logging.getLogger("carcraft-backend")


# ---------------------------------------------------------------------------
# Command
# ---------------------------------------------------------------------------


@dataclass
class CalculateCommand:
    total_amount: float
    down_payment: float
    down_payment_percent: float
    lease_term_months: int
    additional_amount: float | None = None
    buyout_amount: float = 0.0
    buyout_percent: float | None = None
    vehicle_ids: list[UUID] = field(default_factory=list)
    vehicle_price_overrides: dict[UUID, float] = field(default_factory=dict)
    vehicle_quantities: dict[UUID, int] = field(default_factory=dict)
    selected_support: dict[Any, list[Any]] = field(default_factory=dict)
    user: dict[str, Any] | None = None
    persist_history: bool = True
    rates_override: LeasingRates | None = None


@dataclass
class CalculateResult:
    response: dict[str, Any]


# ---------------------------------------------------------------------------
# Internal aggregates — keep handlers below the PLR0915 budget.
# ---------------------------------------------------------------------------


@dataclass
class _SupportOutcome:
    """Result of applying support programs to a vehicle list."""

    effective_total: float
    effective_down_payment: float
    support_breakdown: dict[str, Any] | None = None
    support_per_program: list[dict[str, Any]] = field(default_factory=list)
    support_per_vehicle: list[dict[str, Any]] = field(default_factory=list)
    eligible_by_vehicle_out: list[dict[str, Any]] = field(default_factory=list)
    support_program_details: list[dict[str, Any]] = field(default_factory=list)
    calculations_per_vehicle: list[dict[str, Any]] = field(default_factory=list)
    calculation_without_support: LeasingCalculationResult | None = None
    calculation_without_support_params: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Handler
# ---------------------------------------------------------------------------


async def handle_calculate(
    cmd: CalculateCommand, session: AsyncSession
) -> CalculateResult:
    _validate_additional_amount(cmd)
    params = _build_params(cmd)
    LeasingCalculator.validate_params(params)

    rates = cmd.rates_override or await _resolve_rates(session)
    leasing_company_id = await _resolve_leasing_company_id(session, cmd.user)

    outcome = _SupportOutcome(
        effective_total=params.total_amount,
        effective_down_payment=params.down_payment,
    )
    if params.vehicle_ids:
        outcome = await _build_support_outcome(
            session,
            params,
            rates,
            leasing_company_id,
            outcome,
            additional_amount=cmd.additional_amount,
            actor_role=_actor_role(cmd.user),
        )

    contract_down_payment_global = (
        float(outcome.support_breakdown["contract_down_payment"])
        if outcome.support_breakdown
        else outcome.effective_down_payment
    )
    LeasingCalculator.ensure_advance_within_total(
        contract_down_payment_global, outcome.effective_total
    )

    final_buyout_amount = _resolve_final_buyout(
        params,
        outcome.effective_total,
        contract_down_payment_global,
        outcome.support_breakdown is not None,
    )
    LeasingCalculator.ensure_buyout_within_principal(
        final_buyout_amount, outcome.effective_total, contract_down_payment_global
    )

    client_down_payment_global = (
        float(outcome.support_breakdown["effective_down_payment"])
        if outcome.support_breakdown
        else outcome.effective_down_payment
    )

    calculation = LeasingCalculator.compute_leasing(
        total_amount=outcome.effective_total,
        down_payment=contract_down_payment_global,
        term_months=params.lease_term_months,
        rates=rates,
        buyout_amount=final_buyout_amount,
    )

    response = _build_response(
        params=params,
        outcome=outcome,
        calculation=calculation,
        client_down_payment_global=client_down_payment_global,
        final_buyout_amount=final_buyout_amount,
    )

    if cmd.user is not None and cmd.persist_history:
        await _save_history_safely(
            session,
            user=cmd.user,
            params=params,
            calculation=calculation,
            response=response,
            client_down_payment_global=client_down_payment_global,
            final_buyout_amount=final_buyout_amount,
            effective_total=outcome.effective_total,
        )

    return CalculateResult(response=response)


# ---------------------------------------------------------------------------
# Internals — small, focused helpers
# ---------------------------------------------------------------------------


def _validate_additional_amount(cmd: CalculateCommand) -> None:
    """Validate the explicitly typed subtotal used by mixed calculations."""

    if cmd.additional_amount is None:
        return
    if not 0 <= cmd.additional_amount <= cmd.total_amount:
        raise InvalidCalculationParamsError(
            "Дополнительная сумма должна быть в диапазоне от 0 до общей суммы"
        )


def _build_params(cmd: CalculateCommand) -> CalculationParams:
    return CalculationParams(
        total_amount=cmd.total_amount,
        down_payment=cmd.down_payment,
        down_payment_percent=cmd.down_payment_percent,
        lease_term_months=cmd.lease_term_months,
        buyout_amount=cmd.buyout_amount,
        buyout_percent=cmd.buyout_percent,
        vehicle_ids=list(cmd.vehicle_ids),
        vehicle_price_overrides=dict(cmd.vehicle_price_overrides),
        vehicle_quantities={
            vid: max(1, int(quantity or 1))
            for vid, quantity in cmd.vehicle_quantities.items()
        },
        selected_support=dict(cmd.selected_support),
    )


async def _resolve_rates(session: AsyncSession) -> LeasingRates:
    raw = await repo.get_leasing_rates(session)
    if raw is None:
        if not settings.calculator_use_default_rates_fallback:
            raise LeasingRatesNotConfiguredError()
        return LeasingRates(
            key_rate=settings.calculator_default_key_rate,
            surcharge=settings.calculator_default_surcharge,
            vat_rate=settings.calculator_default_vat_rate,
            profit_tax_rate=settings.calculator_default_profit_tax_rate,
        )
    return LeasingRates(
        key_rate=raw["key_rate"],
        surcharge=raw["surcharge"],
        vat_rate=raw["vat_rate"],
        profit_tax_rate=raw["profit_tax_rate"],
    )


async def _resolve_leasing_company_id(
    session: AsyncSession, user: dict[str, Any] | None
) -> UUID | None:
    if not user:
        return None
    if user.get("role") != "leasing_company" or not user.get("company_id"):
        return None
    result: UUID | None = await repo.get_leasing_company_id_by_company_id(
        session, user["company_id"]
    )
    return result


def _actor_role(user: dict[str, Any] | None) -> str | None:
    role = user.get("role") if user else None
    return role if isinstance(role, str) else None


async def _build_support_outcome(
    session: AsyncSession,
    params: CalculationParams,
    rates: LeasingRates,
    leasing_company_id: UUID | None,
    outcome: _SupportOutcome,
    *,
    additional_amount: float | None,
    actor_role: str | None,
) -> _SupportOutcome:
    vehicle_items = await repo.get_vehicles_with_support_info(
        session, params.vehicle_ids, leasing_company_id=leasing_company_id
    )
    effective_price_rows = await repo.get_vehicles_effective_prices(
        session, params.vehicle_ids
    )
    vehicle_base_map = _build_vehicle_base_map(
        effective_price_rows,
        params.vehicle_price_overrides,
        actor_role=actor_role,
    )
    if not vehicle_base_map:
        return outcome
    LeasingCalculator.ensure_total_amount_within_limits(
        _commerce_base_total(
            vehicle_base_map,
            params,
            additional_amount=additional_amount,
        )
    )
    vehicle_items = _apply_vehicle_base_map_to_items(vehicle_items, vehicle_base_map)

    return await _apply_support(
        session=session,
        params=params,
        rates=rates,
        vehicle_items=vehicle_items,
        vehicle_base_map=vehicle_base_map,
        additional_amount=additional_amount,
    )


def _build_vehicle_base_map(
    rows: list[dict[str, Any]],
    overrides: dict[UUID, float],
    *,
    actor_role: str | None,
) -> dict[UUID, float]:
    vehicle_base_map: dict[UUID, float] = {}
    for row in rows:
        vehicle_id = row["vehicle_id"]
        effective_price = float(row["effective_price"] or 0)
        raw_override = overrides.get(vehicle_id)
        if raw_override is not None and raw_override > 0:
            override_price = Decimal(str(raw_override)).quantize(
                Decimal("0.01"),
                rounding=ROUND_HALF_UP,
            )
            CartItem.ensure_custom_price_allowed(
                actor_role,
                Decimal(str(effective_price)),
            )
            vehicle_base_map[vehicle_id] = float(override_price)
        else:
            vehicle_base_map[vehicle_id] = effective_price
    return vehicle_base_map


def _vehicle_quantity(params: CalculationParams, vehicle_id: UUID) -> int:
    return max(1, int(params.vehicle_quantities.get(vehicle_id) or 1))


def _vehicle_base_total(
    vehicle_base_map: dict[UUID, float], params: CalculationParams
) -> float:
    return sum(
        base_price * _vehicle_quantity(params, vehicle_id)
        for vehicle_id, base_price in vehicle_base_map.items()
    )


def _commerce_base_total(
    vehicle_base_map: dict[UUID, float],
    params: CalculationParams,
    *,
    additional_amount: float | None,
) -> float:
    """Combine authoritative vehicle prices with an explicit extra subtotal.

    ``additional_amount`` contains selected special-equipment lines and
    vehicle options. Callers that omit it keep the legacy greater-of-request-
    or-vehicle behaviour.
    """

    vehicle_base_total = _vehicle_base_total(vehicle_base_map, params)
    if additional_amount is not None:
        return vehicle_base_total + additional_amount
    return max(float(params.total_amount), vehicle_base_total)


def _apply_vehicle_base_map_to_items(
    vehicle_items: list[dict[str, Any]], vehicle_base_map: dict[UUID, float]
) -> list[dict[str, Any]]:
    updated_items: list[dict[str, Any]] = []
    for item in vehicle_items:
        vehicle_id = item["vehicle_id"]
        updated_items.append(
            {
                **item,
                "base_price": vehicle_base_map.get(
                    vehicle_id, float(item.get("base_price") or 0)
                ),
            }
        )
    return updated_items


def _resolve_final_buyout(
    params: CalculationParams,
    effective_total: float,
    contract_down_payment_global: float,
    has_support: bool,
) -> float:
    if params.buyout_amount:
        return float(params.buyout_amount)
    if params.buyout_percent is None:
        return 0.0
    if has_support:
        return round(
            (effective_total - contract_down_payment_global)
            * (params.buyout_percent / 100)
        )
    return round(effective_total * (params.buyout_percent / 100))


def _build_response(
    *,
    params: CalculationParams,
    outcome: _SupportOutcome,
    calculation: LeasingCalculationResult,
    client_down_payment_global: float,
    final_buyout_amount: float,
) -> dict[str, Any]:
    down_payment_percentage = (
        float(outcome.support_breakdown["client_down_payment_percent"])
        if outcome.support_breakdown
        else _percent_or_default(
            client_down_payment_global,
            outcome.effective_total,
            params.down_payment_percent,
        )
    )
    response: dict[str, Any] = {
        "calculation": calculation.to_camel_dict(),
        "calculation_parameters": {
            "total_amount": round(outcome.effective_total),
            "down_payment": round(client_down_payment_global),
            "down_payment_percent": down_payment_percentage,
            "lease_term_months": params.lease_term_months,
            "buyout_amount": round(final_buyout_amount),
            "buyout_percent": _resolve_buyout_percent_for_response(
                params, outcome.effective_total, final_buyout_amount
            ),
        },
    }
    if outcome.support_breakdown:
        response["support"] = outcome.support_breakdown
        if (
            outcome.calculation_without_support is not None
            and outcome.calculation_without_support_params is not None
        ):
            response["calculation_without_support"] = {
                "calculation": outcome.calculation_without_support.to_camel_dict(),
                "calculation_parameters": outcome.calculation_without_support_params,
            }
        response["support_per_program"] = outcome.support_per_program
        response["support_per_vehicle"] = outcome.support_per_vehicle
        response["eligible_support_program_ids_by_vehicle"] = (
            outcome.eligible_by_vehicle_out
        )
        response["support_program_details"] = outcome.support_program_details
        response["calculations_per_vehicle"] = outcome.calculations_per_vehicle
    return response


def _percent_or_default(numerator: float, denominator: float, fallback: float) -> float:
    if denominator <= 0:
        return fallback
    return round((numerator / denominator) * 10000) / 100


def _resolve_buyout_percent_for_response(
    params: CalculationParams, effective_total: float, final_buyout_amount: float
) -> float:
    if params.buyout_percent is not None:
        return params.buyout_percent
    if final_buyout_amount > 0 and effective_total > 0:
        return round((final_buyout_amount / effective_total) * 10000) / 100
    return 0.0


async def _save_history_safely(
    session: AsyncSession,
    *,
    user: dict[str, Any],
    params: CalculationParams,
    calculation: LeasingCalculationResult,
    response: dict[str, Any],
    client_down_payment_global: float,
    final_buyout_amount: float,
    effective_total: float,
) -> None:
    try:
        await repo.save_history(
            session,
            {
                "user_id": user["id"],
                "vehicle_ids": _normalize_vehicle_ids_for_db(params.vehicle_ids),
                "total_amount": effective_total,
                "down_payment": client_down_payment_global,
                "down_payment_percent": response["calculation_parameters"][
                    "down_payment_percent"
                ],
                "lease_term_months": params.lease_term_months,
                "monthly_payment": calculation.monthly_payment,
                "total_cost": calculation.total_cost,
                "markup": calculation.markup,
                "calculation_type": "standard",
                "rate": calculation.rate,
                "total_interest": calculation.total_interest,
                "buyout_amount": final_buyout_amount,
                "vat_refund": calculation.vat_refund,
                "profit_tax_savings": calculation.profit_tax_savings,
                "total_savings": calculation.total_savings,
            },
        )
    except Exception:
        logger.exception("Failed to save calculation history")


def _normalize_vehicle_ids_for_db(vehicle_ids: list[UUID]) -> list[UUID]:
    """Pass through UUID vehicle IDs for storage."""
    return [v for v in vehicle_ids if v is not None]


# ---------------------------------------------------------------------------
# Support-program math
# ---------------------------------------------------------------------------


@dataclass
class _SupportContext:
    params: CalculationParams
    rates: LeasingRates
    vehicle_base_map: dict[UUID, float]
    vehicle_items: list[dict[str, Any]]
    chosen_by_vehicle: dict[UUID, set[UUID]]
    eligible_by_vehicle: dict[UUID, set[UUID]]
    program_map: dict[UUID, dict[str, Any]] = field(default_factory=dict)
    vehicle_map: dict[UUID, dict[str, Any]] = field(default_factory=dict)
    vehicle_totals: dict[UUID, dict[str, float]] = field(default_factory=dict)
    discount_total: float = 0.0
    dealer_commission_total: float = 0.0
    down_payment_support_total: float = 0.0
    interest_support_total: float = 0.0


async def _apply_support(
    *,
    session: AsyncSession,
    params: CalculationParams,
    rates: LeasingRates,
    vehicle_items: list[dict[str, Any]],
    vehicle_base_map: dict[UUID, float],
    additional_amount: float | None,
) -> _SupportOutcome:
    eligible_by_vehicle = _compute_eligibility(vehicle_items, vehicle_base_map)
    chosen_by_vehicle = await _choose_programs(
        session,
        params,
        eligible_by_vehicle,
    )
    eligible_by_vehicle_out = [
        {"vehicle_id": vid, "program_ids": sorted(progs)}
        for vid, progs in eligible_by_vehicle.items()
    ]
    all_eligible = sorted({pid for s in eligible_by_vehicle.values() for pid in s})
    raw_support_program_details = (
        await repo.get_support_program_details_by_ids(session, all_eligible)
        if all_eligible
        else []
    )

    ctx = _SupportContext(
        params=params,
        rates=rates,
        vehicle_base_map=vehicle_base_map,
        vehicle_items=vehicle_items,
        chosen_by_vehicle=chosen_by_vehicle,
        eligible_by_vehicle=eligible_by_vehicle,
        vehicle_totals={
            vid: {
                "vehicleDiscount": 0.0,
                "dealerCommission": 0.0,
                "downPaymentSupport": 0.0,
                "interestSupport": 0.0,
            }
            for vid in vehicle_base_map
        },
    )

    _apply_vehicle_discounts(ctx)
    _apply_down_payment_and_interest(ctx)
    support_program_details = [
        summary
        for vehicle_summaries in build_applicable_support_programs(
            vehicle_items,
            raw_support_program_details,
            down_payment_percent=params.down_payment_percent,
            vehicle_discount_support_by_vehicle={
                vehicle_id: totals["vehicleDiscount"]
                for vehicle_id, totals in ctx.vehicle_totals.items()
            },
        ).values()
        for summary in vehicle_summaries
    ]

    vehicle_base_total = _vehicle_base_total(vehicle_base_map, params)
    base_total = _commerce_base_total(
        vehicle_base_map,
        params,
        additional_amount=additional_amount,
    )
    calculations_per_vehicle = _per_vehicle_calculations(ctx, vehicle_base_total)
    breakdown = _build_breakdown(ctx, base_total)
    no_support_calc, no_support_params = _without_support_calculation(ctx, base_total)

    return _SupportOutcome(
        effective_total=breakdown["effective_total"],
        effective_down_payment=breakdown["effective_down_payment"],
        support_breakdown=breakdown,
        support_per_program=_program_map_to_list(ctx.program_map),
        support_per_vehicle=_vehicle_map_to_list(ctx.vehicle_map),
        eligible_by_vehicle_out=eligible_by_vehicle_out,
        support_program_details=support_program_details,
        calculations_per_vehicle=calculations_per_vehicle,
        calculation_without_support=no_support_calc,
        calculation_without_support_params=no_support_params,
    )


def _compute_eligibility(
    vehicle_items: list[dict[str, Any]], vehicle_base_map: dict[UUID, float]
) -> dict[UUID, set[UUID]]:
    eligible: dict[UUID, set[UUID]] = {vid: set() for vid in vehicle_base_map}
    for item in vehicle_items:
        vid = item["vehicle_id"]
        pid = item["support_program_id"]
        if vid in eligible and pid is not None:
            eligible[vid].add(pid)
    return eligible


async def _choose_programs(
    session: AsyncSession,
    params: CalculationParams,
    eligible: dict[UUID, set[UUID]],
) -> dict[UUID, set[UUID]]:
    """Resolve and validate the selected support set for every vehicle."""

    per_vehicle_selected: dict[UUID, set[UUID]] = {}
    for veh_key, arr in (params.selected_support or {}).items():
        try:
            vid = UUID(str(veh_key))
        except (TypeError, ValueError) as exc:
            raise InvalidCalculationParamsError(
                f"Некорректный идентификатор автомобиля: {veh_key}"
            ) from exc
        if vid not in eligible:
            raise InvalidCalculationParamsError(
                f"Автомобиль {vid} отсутствует в текущем расчёте"
            )
        progs: set[UUID] = set()
        for pid in arr:
            if pid is None:
                continue
            try:
                progs.add(UUID(str(pid)))
            except (TypeError, ValueError) as exc:
                raise InvalidCalculationParamsError(
                    f"Некорректный идентификатор программы поддержки: {pid}"
                ) from exc
        if progs:
            per_vehicle_selected[vid] = progs

    chosen: dict[UUID, set[UUID]] = {}
    for vid, eligible_progs in eligible.items():
        if params.selected_support:
            requested = per_vehicle_selected.get(vid)
            if not requested:
                continue
            unavailable = requested - eligible_progs
            if unavailable:
                program_ids = ", ".join(str(pid) for pid in sorted(unavailable))
                raise InvalidCalculationParamsError(
                    "Программы поддержки неприменимы к автомобилю "
                    f"{vid}: {program_ids}"
                )
            chosen[vid] = requested
        elif eligible_progs:
            chosen[vid] = {min(eligible_progs)}

    await _validate_compatibility(session, chosen)
    return chosen


async def _validate_compatibility(
    session: AsyncSession,
    chosen_by_vehicle: dict[UUID, set[UUID]],
) -> None:
    multi_program_ids = {
        program_id
        for selected in chosen_by_vehicle.values()
        if len(selected) > 1
        for program_id in selected
    }
    if not multi_program_ids:
        return

    flags = await support_repository.get_program_compatibility_flags(
        session,
        sorted(multi_program_ids),
    )
    adjacency = await support_repository.get_compatibility_by_program_ids(
        session,
        sorted(multi_program_ids),
    )
    for vehicle_id, selected in chosen_by_vehicle.items():
        if len(selected) < 2:
            continue
        if not are_support_programs_pairwise_compatible(
            list(selected),
            flags,
            adjacency,
        ):
            raise InvalidCalculationParamsError(
                "Выбранные программы поддержки несовместимы для автомобиля "
                f"{vehicle_id}"
            )


def _is_selected(
    item: dict[str, Any], chosen_by_vehicle: dict[UUID, set[UUID]]
) -> bool:
    chosen = chosen_by_vehicle.get(item["vehicle_id"])
    if not chosen:
        return False
    pid = item["support_program_id"]
    return pid is not None and pid in chosen


def _register_program(
    program_map: dict[UUID, dict[str, Any]],
    program_id: UUID | None,
    vehicle_id: UUID,
    type_: str | None,
    base_amount: float,
    amount: float,
    quantity: int,
) -> None:
    if not program_id or amount <= 0:
        return
    prog = program_map.get(program_id)
    if not prog:
        prog = {
            "support_program_id": program_id,
            "type": type_,
            "totals": {"amount": 0.0},
            "per_vehicle": {},
        }
        program_map[program_id] = prog
    prog["totals"]["amount"] += amount * quantity
    bucket = prog["per_vehicle"].setdefault(
        vehicle_id,
        {"vehicle_id": vehicle_id, "base_amount": 0.0, "support_amount": 0.0},
    )
    bucket["base_amount"] += base_amount or 0
    bucket["support_amount"] += amount


def _register_vehicle(
    vehicle_map: dict[UUID, dict[str, Any]],
    vehicle_id: UUID,
    base_price: float,
    program_id: UUID | None,
    type_: str | None,
    amount: float,
) -> None:
    if amount <= 0:
        return
    veh = vehicle_map.setdefault(
        vehicle_id,
        {
            "vehicle_id": vehicle_id,
            "base_price": base_price or 0,
            "applied_supports": [],
        },
    )
    veh["applied_supports"].append(
        {"support_program_id": program_id, "type": type_, "amount": amount}
    )


def _apply_vehicle_discounts(ctx: _SupportContext) -> None:
    """Pass 1: programs that reduce vehicle price (discount/dealer-invoice)."""
    for item in ctx.vehicle_items:
        if not _is_selected(item, ctx.chosen_by_vehicle):
            continue
        type_ = item.get("support_type")
        params_support = item.get("support_params")
        if not type_ or not params_support:
            continue
        if type_ not in SUPPORT_TYPE_VEHICLE_DISCOUNT:
            continue
        base_price = float(item.get("base_price") or 0)
        program_id: UUID | None = item["support_program_id"]
        vid = item["vehicle_id"]
        quantity = _vehicle_quantity(ctx.params, vid)
        amount = LeasingCalculator.compute_support_from_params(
            params_support, base_price
        )
        if amount <= 0:
            continue
        total_amount = amount * quantity
        ctx.discount_total += total_amount
        if type_ == SUPPORT_TYPE_DEALER_COMMISSION:
            ctx.dealer_commission_total += total_amount
        _register_program(
            ctx.program_map, program_id, vid, type_, base_price, amount, quantity
        )
        _register_vehicle(ctx.vehicle_map, vid, base_price, program_id, type_, amount)
        ctx.vehicle_totals[vid]["vehicleDiscount"] += amount
        if type_ == SUPPORT_TYPE_DEALER_COMMISSION:
            ctx.vehicle_totals[vid]["dealerCommission"] += amount


def _apply_down_payment_and_interest(ctx: _SupportContext) -> None:
    """Pass 2: down-payment compensation + interest compensation."""
    pct = (ctx.params.down_payment_percent or 0) / 100
    for item in ctx.vehicle_items:
        if not _is_selected(item, ctx.chosen_by_vehicle):
            continue
        type_ = item.get("support_type")
        params_support = item.get("support_params")
        if not type_ or not params_support:
            continue
        if type_ in SUPPORT_TYPE_VEHICLE_DISCOUNT:
            continue
        base_price = float(item.get("base_price") or 0)
        program_id: UUID | None = item["support_program_id"]
        vid = item["vehicle_id"]

        if type_ == SUPPORT_TYPE_DOWN_PAYMENT:
            _apply_one_down_payment_support(
                ctx,
                item=item,
                params_support=params_support,
                type_=type_,
                base_price=base_price,
                program_id=program_id,
                vid=vid,
                pct=pct,
            )
        elif type_ == SUPPORT_TYPE_INTEREST:
            _apply_one_interest_support(
                ctx,
                params_support=params_support,
                type_=type_,
                base_price=base_price,
                program_id=program_id,
                vid=vid,
            )


def _apply_one_down_payment_support(
    ctx: _SupportContext,
    *,
    item: dict[str, Any],
    params_support: dict[str, Any],
    type_: str,
    base_price: float,
    program_id: UUID | None,
    vid: UUID,
    pct: float,
) -> None:
    del item
    vst = ctx.vehicle_totals[vid]
    eff_price = max(0.0, base_price - vst["vehicleDiscount"])
    down_for_vehicle = round(eff_price * pct)
    amount = LeasingCalculator.compute_support_from_params(
        params_support, down_for_vehicle
    )
    if amount <= 0:
        return
    quantity = _vehicle_quantity(ctx.params, vid)
    ctx.down_payment_support_total += amount * quantity
    _register_program(
        ctx.program_map, program_id, vid, type_, down_for_vehicle, amount, quantity
    )
    _register_vehicle(ctx.vehicle_map, vid, base_price, program_id, type_, amount)
    vst["downPaymentSupport"] += amount


def _apply_one_interest_support(
    ctx: _SupportContext,
    *,
    params_support: dict[str, Any],
    type_: str,
    base_price: float,
    program_id: UUID | None,
    vid: UUID,
) -> None:
    amount = LeasingCalculator.compute_support_from_params(params_support, base_price)
    if amount <= 0:
        return
    quantity = _vehicle_quantity(ctx.params, vid)
    ctx.interest_support_total += amount * quantity
    _register_program(
        ctx.program_map, program_id, vid, type_, base_price, amount, quantity
    )
    _register_vehicle(ctx.vehicle_map, vid, base_price, program_id, type_, amount)
    ctx.vehicle_totals[vid]["interestSupport"] += amount


def _per_vehicle_calculations(
    ctx: _SupportContext, base_total: float
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for vid, base_price in ctx.vehicle_base_map.items():
        vst = ctx.vehicle_totals[vid]
        amounts = LeasingCalculator.compute_support_payment_amounts(
            base_total=base_price,
            down_payment_percent=ctx.params.down_payment_percent,
            vehicle_discount_support=vst["vehicleDiscount"],
            down_payment_support=vst["downPaymentSupport"],
            interest_support=vst["interestSupport"],
        )
        eff_total = amounts.effective_total
        base_down_v = amounts.contract_down_payment
        client_down_v = amounts.client_down_payment
        veh_buyout = _vehicle_buyout(
            ctx.params, eff_total, base_down_v, base_price, base_total
        )
        veh_calc = LeasingCalculator.compute_leasing(
            total_amount=eff_total,
            down_payment=base_down_v,
            term_months=ctx.params.lease_term_months,
            rates=ctx.rates,
            buyout_amount=veh_buyout,
        )

        base_down_v_w = amounts.contract_down_payment
        veh_buyout_w = _vehicle_buyout(
            ctx.params, base_price, base_down_v_w, base_price, base_total
        )
        veh_calc_without = LeasingCalculator.compute_leasing(
            total_amount=base_price,
            down_payment=base_down_v_w,
            term_months=ctx.params.lease_term_months,
            rates=ctx.rates,
            buyout_amount=veh_buyout_w,
        )
        result.append(
            {
                "vehicle_id": vid,
                "calculation": veh_calc.to_camel_dict(),
                "calculation_without_support": veh_calc_without.to_camel_dict(),
                "support_breakdown": {
                    "vehicle_discount_support": round(vst["vehicleDiscount"]),
                    "dealer_commission_support": round(vst["dealerCommission"]),
                    "down_payment_support": round(vst["downPaymentSupport"]),
                    "interest_support": round(vst["interestSupport"]),
                    "contract_down_payment": round(base_down_v),
                    "client_down_payment": round(client_down_v),
                },
            }
        )
    return result


def _vehicle_buyout(
    params: CalculationParams,
    eff_total: float,
    base_down_v: float,
    base_price: float,
    base_total: float,
) -> float:
    if params.buyout_percent is not None and params.buyout_percent > 0:
        return round((eff_total - base_down_v) * (params.buyout_percent / 100))
    if params.buyout_amount and base_total > 0:
        return round((base_price / base_total) * params.buyout_amount)
    return 0.0


def _build_breakdown(ctx: _SupportContext, base_total: float) -> dict[str, Any]:
    amounts = LeasingCalculator.compute_support_payment_amounts(
        base_total=base_total,
        down_payment_percent=ctx.params.down_payment_percent,
        vehicle_discount_support=ctx.discount_total,
        down_payment_support=ctx.down_payment_support_total,
        interest_support=ctx.interest_support_total,
    )
    return {
        "base_total": amounts.base_total,
        "vehicle_discount_support": round(ctx.discount_total),
        "dealer_commission_support": round(ctx.dealer_commission_total),
        "down_payment_support": round(ctx.down_payment_support_total),
        "interest_support": round(ctx.interest_support_total),
        "effective_total": amounts.effective_total,
        "contract_down_payment": amounts.contract_down_payment,
        "effective_down_payment": amounts.client_down_payment,
        "client_down_payment_percent": amounts.client_down_payment_percent,
    }


def _without_support_calculation(
    ctx: _SupportContext, base_total: float
) -> tuple[LeasingCalculationResult | None, dict[str, Any] | None]:
    if base_total <= 0:
        return None, None
    pct = (ctx.params.down_payment_percent or 0) / 100
    base_down_payment = round(base_total * pct)
    base_buyout_amount = ctx.params.buyout_amount or 0.0
    if not ctx.params.buyout_amount and ctx.params.buyout_percent is not None:
        base_buyout_amount = round(
            (base_total - base_down_payment) * (ctx.params.buyout_percent / 100)
        )
    calc = LeasingCalculator.compute_leasing(
        total_amount=base_total,
        down_payment=base_down_payment,
        term_months=ctx.params.lease_term_months,
        rates=ctx.rates,
        buyout_amount=base_buyout_amount,
    )
    params_dict = {
        "total_amount": round(base_total),
        "down_payment": round(base_down_payment),
        "down_payment_percent": ctx.params.down_payment_percent,
        "lease_term_months": ctx.params.lease_term_months,
        "buyout_amount": round(base_buyout_amount),
        "buyout_percent": (
            ctx.params.buyout_percent
            if ctx.params.buyout_percent is not None
            else (
                round((base_buyout_amount / base_total) * 10000) / 100
                if base_buyout_amount > 0 and base_total > 0
                else 0
            )
        ),
    }
    return calc, params_dict


def _program_map_to_list(
    program_map: dict[UUID, dict[str, Any]],
) -> list[dict[str, Any]]:
    return [
        {
            "support_program_id": prog["support_program_id"],
            "type": prog["type"],
            "totals": {"amount": round(prog["totals"]["amount"])},
            "per_vehicle": [
                {
                    "vehicle_id": pv["vehicle_id"],
                    "base_amount": round(pv["base_amount"]),
                    "support_amount": round(pv["support_amount"]),
                }
                for pv in prog["per_vehicle"].values()
            ],
        }
        for prog in program_map.values()
    ]


def _vehicle_map_to_list(
    vehicle_map: dict[UUID, dict[str, Any]],
) -> list[dict[str, Any]]:
    return [
        {
            "vehicle_id": v["vehicle_id"],
            "base_price": round(v["base_price"]),
            "applied_supports": [
                {
                    "support_program_id": s["support_program_id"],
                    "type": s["type"],
                    "amount": round(s["amount"]),
                }
                for s in v["applied_supports"]
            ],
        }
        for v in vehicle_map.values()
    ]


def _opt_int(value: Any) -> UUID | None:
    return value if value is not None else None


async def compute_canonical_application_calculation(
    session: AsyncSession,
    *,
    total_amount: Decimal | float | None,
    down_payment_percent: Decimal | float | None,
    lease_term_months: int | None,
    buyout_amount: Decimal | float = 0,
) -> dict[str, Any]:
    """Calculate canonical leasing financials for an application.

    Returns empty dict if required inputs are missing or non-positive.
    """
    if (
        total_amount is None
        or down_payment_percent is None
        or lease_term_months is None
    ):
        return {}

    try:
        total = float(total_amount)
        percent = float(down_payment_percent)
        term = int(lease_term_months)
        buyout = float(buyout_amount or 0)
    except (ValueError, TypeError):
        return {}

    if total <= 0 or percent <= 0 or term <= 0:
        return {}

    down_payment = round(total * (percent / 100.0), 2)
    rates = await _resolve_rates(session)
    calc = LeasingCalculator.compute_leasing(
        total_amount=total,
        down_payment=down_payment,
        term_months=term,
        rates=rates,
        buyout_amount=buyout,
    )
    return {
        "total_amount": Decimal(str(round(total, 2))),
        "down_payment": Decimal(str(down_payment)),
        "down_payment_percent": Decimal(str(round(percent, 2))),
        "lease_term_months": Decimal(str(term)),
        "monthly_payment": Decimal(str(calc.monthly_payment)),
        "total_cost": Decimal(str(calc.total_cost)),
        "markup": Decimal(str(calc.markup)),
        "rate": Decimal(str(calc.rate)),
        "total_interest": Decimal(str(calc.total_interest)),
        "buyout_amount": Decimal(str(calc.buyout_amount)),
        "vat_refund": Decimal(str(calc.vat_refund)),
        "profit_tax_savings": Decimal(str(calc.profit_tax_savings)),
        "total_savings": Decimal(str(calc.total_savings)),
    }
