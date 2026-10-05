"""Exact editable deal terms; program formulas remain immutable historical data."""

from decimal import ROUND_HALF_UP, Decimal, DecimalException, localcontext
from typing import Any, cast

from domain.monetization.errors import MonetizationValidation
from domain.monetization.identifiers import entity_id
from domain.monetization.programs import (
    MONEY_LIMIT,
    MONEY_STEP,
    positive_decimal,
    validate_linked_totals,
)

PERCENT_STEP = Decimal("0.01")
INPUT_STEP = Decimal("0.00000001")
PERCENT_LIMIT = Decimal("1000000000000000000000000000000")
Record = dict[str, Any]


def base_type(row: Record) -> str:
    """A fixed condition without a base uses the property's explicit equivalent."""
    return (
        "expense_amount"
        if row.get("condition_base_type") == "expense_amount"
        else "property_value"
    )


def calculation_base(
    row: Record, amounts: dict[Any, Record], property_value: Decimal
) -> Decimal | None:
    if base_type(row) == "property_value":
        return property_value
    reference = row.get("expense_ref_amount_id")
    expense = amounts.get(entity_id(reference)) if reference is not None else None
    if expense is None or expense["side"] != "expense":
        return None
    return cast("Decimal", expense["amount"])


def derived_percent(amount: Decimal, base: Decimal | None) -> Decimal | None:
    if base is None or base <= 0:
        return None
    with localcontext() as arithmetic:
        arithmetic.prec = 80
        result = (amount * Decimal("100") / base).quantize(
            PERCENT_STEP, rounding=ROUND_HALF_UP
        )
    if result >= PERCENT_LIMIT:
        raise MonetizationValidation("Процент превышает допустимую точность")
    return result


def effective_terms(
    row: Record, amounts: dict[Any, Record], property_value: Decimal
) -> tuple[Decimal, Decimal | None, str]:
    percent = row.get("percent")
    if percent is None:
        percent = derived_percent(
            row["amount"], calculation_base(row, amounts, property_value)
        )
    return row["amount"], percent, row.get("input_mode") or "amount"


def _change_index(amounts: dict[Any, Record], changes: list[Record]) -> dict[Any, Record]:
    indexed: dict[Any, Record] = {}
    for change in changes:
        amount_id = entity_id(change.get("deal_participant_amount_id"))
        if amount_id not in amounts or amount_id in indexed:
            raise MonetizationValidation(
                "Строка корректировки не найдена или указана несколько раз"
            )
        mode = change.get("input_mode", "amount")
        if mode not in {"percent", "amount"}:
            raise MonetizationValidation("Выберите ввод процента или суммы")
        field = "new_percent" if mode == "percent" else "new_value"
        other = "new_value" if mode == "percent" else "new_percent"
        if change.get(other) is not None:
            raise MonetizationValidation("Передайте только процент или только сумму")
        value = positive_decimal(change.get(field), field)
        limit = PERCENT_LIMIT if mode == "percent" else MONEY_LIMIT
        if value >= limit or value != value.quantize(INPUT_STEP, rounding=ROUND_HALF_UP):
            raise MonetizationValidation("Недопустимая точность процента или суммы")
        step = PERCENT_STEP if mode == "percent" else MONEY_STEP
        normalized = value.quantize(step, rounding=ROUND_HALF_UP)
        if normalized <= 0 or normalized >= limit:
            raise MonetizationValidation(
                "После округления значение должно быть положительным и допустимым"
            )
        indexed[amount_id] = dict(change, input_mode=mode, **{field: normalized})
    return indexed


def _new_terms(
    row: Record, change: Record | None, base: Decimal | None
) -> tuple[Decimal, Decimal | None, str, Decimal]:
    mode = change["input_mode"] if change else row.get("input_mode") or "amount"
    if mode == "percent":
        percent = (
            change["new_percent"] if change else
            positive_decimal(row.get("percent"), "new_percent")
        )
        if base is None or base <= 0:
            raise MonetizationValidation(
                "Для изменения процента требуется положительная база расчёта"
            )
        raw = base * percent / Decimal("100")
    else:
        raw = change["new_value"] if change else row["amount"]
        percent = None
    rounded = (
        raw if change is None and mode == "amount"
        else raw.quantize(MONEY_STEP, rounding=ROUND_HALF_UP)
    )
    if rounded >= MONEY_LIMIT or rounded < 0 or (change is not None and rounded == 0):
        raise MonetizationValidation("Новая сумма должна быть положительной и допустимой")
    if mode == "percent" and rounded == 0:
        raise MonetizationValidation("Сумма по новому проценту округляется к нулю")
    if mode == "amount":
        percent = derived_percent(rounded, base)
    return rounded, percent, mode, raw


def apply_terms(deal: Record, changes: list[Record]) -> list[Record]:
    """Apply expenses before incomes, preserving the chosen authoritative input.

    Historical null terms are compared through their effective amount-mode value.
    Merely materializing those defaults is not a financial change.
    """
    amounts = {entity_id(row["id"]): row for row in deal["amounts"]}
    property_value = deal["base_amount"]
    try:
        with localcontext() as arithmetic:
            arithmetic.prec = 80
            indexed = _change_index(amounts, changes)
            previous = {
                amount_id: effective_terms(row, amounts, property_value)
                for amount_id, row in amounts.items()
            }
            old_bases = {
                amount_id: calculation_base(row, amounts, property_value)
                for amount_id, row in amounts.items()
            }
            unrounded = {amount_id: row["amount"] for amount_id, row in amounts.items()}
            entries = []
            for row in sorted(amounts.values(), key=lambda item: item["side"] != "expense"):
                amount_id = entity_id(row["id"])
                change = indexed.get(amount_id)
                base = calculation_base(row, amounts, property_value)
                if change is None and (
                    base == old_bases[amount_id] or row["amount"] == 0
                ):
                    continue
                if (
                    change is not None and change["input_mode"] == "amount"
                    and previous[amount_id][2] == "amount"
                    and change["new_value"] == row["amount"]
                    and base == old_bases[amount_id]
                ):
                    # Repeating authoritative money must not shorten a saved
                    # historical equivalent percentage merely to materialize it.
                    continue
                amount, percent, mode, raw = _new_terms(row, change, base)
                unrounded[amount_id] = raw
                if (amount, percent, mode) == previous[amount_id]:
                    continue
                entries.append({
                    "deal_participant_amount_id": amount_id,
                    "old_value": row["amount"],
                    "new_value": amount,
                    "old_percent": row.get("percent"),
                    "new_percent": percent,
                    "old_input_mode": row.get("input_mode"),
                    "new_input_mode": mode,
                })
                row.update(amount=amount, percent=percent, input_mode=mode)
            validate_linked_totals(deal["amounts"], unrounded)
    except DecimalException as exc:
        raise MonetizationValidation("Суммы превышают допустимую точность расчёта") from exc
    return entries
