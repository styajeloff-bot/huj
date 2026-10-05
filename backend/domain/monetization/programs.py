"""Validation, selection and financial calculation of monetization conditions."""

from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, DecimalException, localcontext
from fractions import Fraction
from math import floor
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

from domain.monetization.errors import MonetizationConflict, MonetizationValidation
from domain.monetization.identifiers import entity_id, same_entity

SOURCES = frozenset(
    {"platform", "dealer_account", "exchange", "dealer_site", "distributor_site"}
)
PARTICIPANTS = frozenset({"leasing", "dealer", "distributor", "platform"})
CURRENT_RULES_VERSION = 2
CURRENT_VEHICLE_FILTER_VERSION = 2
MONEY_STEP = Decimal("0.01")
MONEY_LIMIT = Decimal("10000000000000000")


def _rules_version(program: dict[str, Any]) -> int:
    version = program.get("rules_version", 1)
    if (
        isinstance(version, bool) or not isinstance(version, int)
        or version not in {1, CURRENT_RULES_VERSION}
    ):
        raise MonetizationValidation("Неизвестная версия правил монетизации")
    return version


def _vehicle_filter_version(program: dict[str, Any]) -> int:
    version = program.get("vehicle_filter_version", 1)
    if (
        isinstance(version, bool) or not isinstance(version, int)
        or version not in {1, CURRENT_VEHICLE_FILTER_VERSION}
    ):
        raise MonetizationValidation("Неизвестная версия фильтров транспорта")
    return version


def positive_decimal(value: Any, name: str) -> Decimal:
    """Accept exact, positive finite financial input, never binary floats."""
    name = {
        "value": "Значение",
        "min": "Минимум",
        "max": "Максимум",
        "base_amount": "Стоимость имущества",
        "new_value": "Новая сумма",
    }.get(name, name)
    if not isinstance(value, Decimal) or not value.is_finite() or value <= 0:
        raise MonetizationValidation(
            f"{name}: требуется положительное конечное десятичное число"
        )
    return value


def _validate_row(row: dict[str, Any], side: str, rules_version: int) -> None:
    if row.get("participant_type") not in PARTICIPANTS:
        raise MonetizationValidation("Выбран недоступный участник монетизации")
    if row.get("calc_type") not in {"percent", "amount"}:
        raise MonetizationValidation("Выберите процент или фиксированную сумму")
    allowed_bases = {"property_value", "none"}
    if side == "income":
        allowed_bases.add("expense_amount")
    if row.get("base_type") not in allowed_bases:
        raise MonetizationValidation("Выбрана недопустимая база расчёта")
    if row["base_type"] == "none" and row["calc_type"] != "amount":
        raise MonetizationValidation("Для процента необходимо выбрать базу расчёта")
    positive_decimal(row.get("value"), "value")
    for field in ("min", "max"):
        if row.get(field) is not None:
            positive_decimal(row[field], field)
    if (
        row.get("min") is not None
        and row.get("max") is not None
        and row["min"] > row["max"]
    ):
        raise MonetizationValidation("Минимум не может превышать максимум")
    if row.get("expense_ref") is not None:
        if side == "expense":
            raise MonetizationValidation("Расход не может ссылаться на другой расход")
        if rules_version == 1 and row["base_type"] != "expense_amount":
            raise MonetizationValidation(
                "Связь с расходом допустима только для расчёта от суммы расхода"
            )


def _expense_index(expenses: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for expense in expenses:
        keys = {
            str(expense[key])
            for key in ("local_id", "id")
            if expense.get(key) is not None
        }
        for key in keys:
            if not key or key in result:
                raise MonetizationValidation(
                    "Идентификаторы расходов в блоке должны быть непустыми и уникальными"
                )
            result[key] = expense
    return result


def validate_program(program: dict[str, Any]) -> None:
    """Validate structure and arithmetic contradictions known before a deal."""
    _validate_structure(program)
    for source in program["sources"]:
        if _rules_version(program) == 1:
            _validate_known_arithmetic(source)
        else:
            _validate_grouped_arithmetic(source)


def _validate_structure(program: dict[str, Any]) -> None:
    rules_version = _rules_version(program)
    _vehicle_filter_version(program)
    if not program.get("name") or not program.get("leasing_company_id"):
        raise MonetizationValidation("Укажите название условий и лизинговую компанию")
    for field in (
        "leasing_company_id",
        "dealer_company_id",
        "distributor_company_id",
        "support_program_id",
    ):
        if program.get(field) is not None:
            entity_id(program[field])
    start, end = program.get("period_start"), program.get("period_end")
    if not isinstance(start, date) or isinstance(start, datetime):
        raise MonetizationValidation("Укажите дату начала действия условий")
    if end is not None and (
        not isinstance(end, date) or isinstance(end, datetime) or end < start
    ):
        raise MonetizationValidation("Окончание периода не может быть раньше начала")
    if program.get("status", "active") not in {"active", "inactive"}:
        raise MonetizationValidation("Недопустимый статус условий")
    if not program.get("sources"):
        raise MonetizationValidation("Добавьте хотя бы один блок источника")
    for source in program["sources"]:
        _validate_source(program, source, rules_version)


def _validate_source(
    program: dict[str, Any], source: dict[str, Any], rules_version: int
) -> None:
    if source.get("source_type") not in SOURCES:
        raise MonetizationValidation("Этот источник пока недоступен")
    if source["source_type"] == "exchange" and (
        program.get("support_program_id") or program.get("support_program_name")
    ):
        raise MonetizationValidation(
            "Для условий с биржей нельзя выбирать программу стимулирования"
        )
    if not source.get("expenses"):
        raise MonetizationValidation(
            "Добавьте хотя бы один расход в каждый блок источника"
        )
    _validate_local_ids(source)
    expenses = _expense_index(source["expenses"])
    for expense in source["expenses"]:
        _validate_row(expense, "expense", rules_version)
    for income in source.get("incomes", []):
        _validate_row(income, "income", rules_version)
        if (
            (
                rules_version == CURRENT_RULES_VERSION
                or income["base_type"] == "expense_amount"
            )
            and str(income.get("expense_ref")) not in expenses
        ):
            raise MonetizationValidation(
                "Ссылка дохода должна указывать на расход в том же блоке"
            )


def select_program(
    programs: list[dict[str, Any]], context: dict[str, Any]
) -> dict[str, Any] | None:
    """Select the unique most specific eligible conditions; absence returns None."""
    day = _context_day(context)
    eligible = [item for item in programs if _matches(item, context, day)]
    if not eligible:
        return None
    best_score = max(_specificity(item) for item in eligible)
    selected = [item for item in eligible if _specificity(item) == best_score]
    if len(selected) != 1:
        candidates = ", ".join(
            f"«{item['name']}» ({item['id']})"
            for item in sorted(selected, key=lambda item: entity_id(item["id"]))
        )
        raise MonetizationConflict(
            "Подбор неоднозначен: найдены условия с одинаковым приоритетом. "
            f"Конфликтующие условия: {candidates}"
        )
    return selected[0]


def _context_day(context: dict[str, Any]) -> date:
    for field in ("leasing_company_id", "dealer_company_id"):
        if not context.get(field):
            raise MonetizationValidation(
                f"В снимке сделки отсутствует обязательный участник: {'ЛК' if field == 'leasing_company_id' else 'дилер'}"
            )
    for field in ("leasing_company_id", "dealer_company_id", "distributor_company_id"):
        if context.get(field) is not None:
            entity_id(context[field])
    if context.get("source_type") not in SOURCES:
        raise MonetizationValidation(
            "Не указан источник сделки или выбран недоступный источник"
        )
    occurred_at = context.get("occurred_at")
    if not isinstance(occurred_at, datetime) or occurred_at.utcoffset() is None:
        raise MonetizationValidation(
            "Момент заключения сделки должен содержать часовой пояс"
        )
    return occurred_at.astimezone(ZoneInfo("Europe/Moscow")).date()


def _specificity(program: dict[str, Any]) -> int:
    fields = (
        "dealer_company_id",
        "distributor_company_id",
        "brand",
        "model",
        "modification",
        "trim",
        "vin",
    )
    return sum(program.get(field) is not None for field in fields) + int(
        bool(program.get("support_program_id") or program.get("support_program_name"))
    )


def _matches(program: dict[str, Any], context: dict[str, Any], day: date) -> bool:
    if (
        program.get("status") != "active"
        or day < program["period_start"]
        or (program.get("period_end") is not None and day > program["period_end"])
    ):
        return False
    for field in ("leasing_company_id", "dealer_company_id", "distributor_company_id"):
        if program.get(field) is not None and not same_entity(
            program[field], context.get(field)
        ):
            return False
    if not any(
        source["source_type"] == context["source_type"] for source in program["sources"]
    ):
        return False
    has_vehicle_filters = any(
        program.get(field) is not None for field in ("brand", "model", "modification", "trim", "vin")
    )
    legacy_trim = _vehicle_filter_version(program) == 1
    vehicles = [
        vehicle
        for vehicle in context.get("vehicles", [])
        if all(
            program.get(field) is None
            or (
                vehicle.get("legacy_trim", vehicle.get("trim"))
                if field == "trim" and legacy_trim else vehicle.get(field)
            ) == program[field]
            for field in ("brand", "model", "modification", "trim", "vin")
        )
    ]
    if has_vehicle_filters and not vehicles:
        return False
    if program.get("support_program_id") or program.get("support_program_name"):
        return _support_matches(program, context, vehicles)
    return True


def _support_matches(
    program: dict[str, Any], context: dict[str, Any], vehicles: list[dict[str, Any]]
) -> bool:
    name = program.get("support_program_name")
    if not name:
        return False
    vehicle_ids = {
        entity_id(vehicle["vehicle_id"])
        for vehicle in vehicles
        if vehicle.get("vehicle_id") is not None
    }
    origins = ("dealer_company_id", "distributor_company_id")
    for support in context.get("supports", []):
        if support.get("name") != name or (
            support.get("vehicle_id") is None
            or entity_id(support["vehicle_id"]) not in vehicle_ids
        ):
            continue
        if not any(support.get(field) is not None for field in origins):
            continue
        if all(
            support.get(field) is None
            or same_entity(support[field], context.get(field))
            for field in origins
        ):
            return True
    return False


def calculate_program(
    program: dict[str, Any], context: dict[str, Any]
) -> list[dict[str, Any]]:
    """Calculate matching blocks using exact bases, clipping, then cent rounding."""
    _validate_structure(program)
    day = _context_day(context)
    base = positive_decimal(context.get("base_amount"), "base_amount")
    if not _matches(program, context, day):
        raise MonetizationConflict("Выбранные условия не подходят к снимку сделки")
    amounts = []
    try:
        with localcontext() as arithmetic:
            arithmetic.prec = 80
            for source in program["sources"]:
                if source["source_type"] == context["source_type"]:
                    amounts.extend(
                        _calculate_source(source, base, _rules_version(program))
                    )
    except DecimalException as exc:
        raise MonetizationValidation(
            "Суммы превышают допустимую точность расчёта"
        ) from exc
    if (
        any(row["participant_type"] == "distributor" for row in amounts)
        and context.get("distributor_company_id") is None
    ):
        raise MonetizationValidation(
            "Для расчёта отсутствует компания дистрибьютора в снимке сделки"
        )
    return amounts


def _compute(row: dict[str, Any], base: Decimal) -> tuple[Decimal, Decimal, str]:
    raw = (
        row["value"]
        if row["calc_type"] == "amount"
        else base * row["value"] / Decimal("100")
    )
    if row.get("min") is not None and raw < row["min"]:
        return raw, row["min"], "min"
    if row.get("max") is not None and raw > row["max"]:
        return raw, row["max"], "max"
    return raw, raw, "none"


def _amount_row(
    source: dict[str, Any],
    row: dict[str, Any],
    side: str,
    base: Decimal,
    expense_id: Any = None,
) -> tuple[dict[str, Any], Decimal]:
    raw, clipped, clip = _compute(row, base)
    rounded = clipped.quantize(MONEY_STEP, rounding=ROUND_HALF_UP)
    if rounded >= MONEY_LIMIT:
        raise MonetizationValidation("Сумма превышает допустимую точность хранения")
    amount = {
        "id": uuid4(),
        "program_source_id": source.get("id"),
        "source_participant_id": row.get("id"),
        "side": side,
        "participant_type": row["participant_type"],
        "expense_ref_amount_id": expense_id,
        "raw_amount": raw,
        "amount": rounded,
        "clip": clip,
        "vat_excluded": row.get("vat_excluded", False),
    }
    return amount, clipped


def _calculate_source(
    source: dict[str, Any], base: Decimal, rules_version: int
) -> list[dict[str, Any]]:
    amounts = []
    expenses: dict[str, tuple[dict[str, Any], Decimal]] = {}
    unrounded: dict[Any, Decimal] = {}
    for expense in source["expenses"]:
        amount, clipped = _amount_row(source, expense, "expense", base)
        amounts.append(amount)
        unrounded[amount["id"]] = clipped
        for field in ("local_id", "id"):
            if expense.get(field) is not None:
                expenses[str(expense[field])] = amount, clipped
    for income in source.get("incomes", []):
        expense_id, income_base = None, base
        if (
            rules_version == CURRENT_RULES_VERSION
            or income["base_type"] == "expense_amount"
        ):
            expense_amount, available = expenses[str(income["expense_ref"])]
            expense_id = expense_amount["id"]
            if income["base_type"] == "expense_amount":
                # The original formula uses the clipped, unrounded expense.
                # Changing monetary precision must not change its calculation base.
                income_base = available
        amount, clipped = _amount_row(source, income, "income", income_base, expense_id)
        amounts.append(amount)
        unrounded[amount["id"]] = clipped
    validate_linked_totals(amounts, unrounded)
    return amounts


def validate_linked_totals(
    amounts: list[dict[str, Any]],
    unrounded: dict[Any, Decimal] | None = None,
) -> None:
    """An expense only funds its own explicitly linked income rows."""
    expenses = {
        entity_id(row["id"]): row for row in amounts if row["side"] == "expense"
    }
    totals: dict[Any, Decimal] = {}
    exact_totals: dict[Any, Decimal] = {}
    for row in amounts:
        reference = row.get("expense_ref_amount_id")
        if row["side"] != "income" or reference is None:
            continue
        reference = entity_id(reference)
        if reference not in expenses:
            raise MonetizationValidation(
                "Ссылка дохода должна указывать на расход этой сделки"
            )
        totals[reference] = totals.get(reference, Decimal("0")) + row["amount"]
        if unrounded is not None:
            exact_totals[reference] = (
                exact_totals.get(reference, Decimal("0")) + unrounded[row["id"]]
            )
    for reference, total in totals.items():
        if unrounded is not None and exact_totals[reference] > unrounded[reference]:
            raise MonetizationConflict(
                "Сумма связанных доходов превышает расход до округления"
            )
        if total > expenses[reference]["amount"]:
            raise MonetizationConflict(
                "После округления сумма связанных доходов превышает расход"
            )


def _validate_grouped_arithmetic(source: dict[str, Any]) -> None:
    """Reject impossible groups without inventing a future property value."""
    expenses = _expense_index(source["expenses"])
    groups: dict[int, list[dict[str, Any]]] = {}
    for income in source.get("incomes", []):
        expense = expenses[str(income["expense_ref"])]
        groups.setdefault(id(expense), []).append(income)
    for expense in source["expenses"]:
        linked = groups.get(id(expense), [])
        if not linked:
            continue
        fixed_expense = _is_fixed_amount(expense)
        if fixed_expense and all(
            _is_fixed_amount(income) or income["base_type"] == "expense_amount"
            for income in linked
        ):
            _validate_fixed_expense(expense, linked)
        elif not _can_fund_group(expense, linked):
            raise MonetizationValidation(
                "Сумма связанных доходов превышает расход при любой допустимой стоимости имущества"
            )


def _is_fixed_amount(row: dict[str, Any]) -> bool:
    return row["calc_type"] == "amount" or (
        row.get("min") is not None and row.get("min") == row.get("max")
    )


def _can_fund_group(expense: dict[str, Any], linked: list[dict[str, Any]]) -> bool:
    """Compare clipped formulas over positive property values, using exact fractions.

    The expense and each income are continuous piecewise affine functions of
    property value. Their clipping boundaries delimit every possible change in
    the slope of income minus expense, including incomes based on that expense.
    Feasibility is checked at these boundaries and along the final affine tail.
    Calculation still checks the actual value and independent cent rounding.
    """
    boundaries = {Fraction(0)}
    for row in [expense, *linked]:
        if row["calc_type"] != "percent":
            continue
        for field in ("min", "max"):
            if row.get(field) is None:
                continue
            boundary = Fraction(row[field]) * 100 / Fraction(row["value"])
            if row is not expense and row["base_type"] == "expense_amount":
                if expense["calc_type"] != "percent":
                    continue
                boundary = boundary * 100 / Fraction(expense["value"])
            boundaries.add(boundary)

    def surplus(property_value: Fraction) -> Fraction:
        available = _exact_income(expense, property_value)
        return sum(
            (
                _exact_income(
                    income,
                    available if income["base_type"] == "expense_amount" else property_value,
                )
                for income in linked
            ),
            Fraction(0),
        ) - available

    maximum = None
    if _is_fixed_amount(expense):
        maximum = _exact_income(expense, Fraction(0))
    elif expense.get("max") is not None:
        maximum = Fraction(expense["max"])
    if maximum is not None:
        minimum_expense = _exact_income(expense, Fraction(0))
        minimum_rounded_income = sum(
            floor(
                _exact_income(
                    income,
                    minimum_expense if income["base_type"] == "expense_amount" else Fraction(0),
                ) * 100 + Fraction(1, 2)
            )
            for income in linked
        )
        if minimum_rounded_income > floor(maximum * 100 + Fraction(1, 2)):
            return False

    # A negative value at zero remains feasible at a small positive value;
    # equality at zero alone cannot prove feasibility because zero is excluded.
    if surplus(Fraction(0)) < 0:
        return True
    if any(value > 0 and surplus(value) <= 0 for value in boundaries):
        return True
    last = max(boundaries)
    last_surplus = surplus(last)
    tail_slope = surplus(last + 1) - last_surplus
    return tail_slope < 0 or (tail_slope == 0 and last_surplus <= 0)


def _validate_known_arithmetic(source: dict[str, Any]) -> None:
    expenses = _expense_index(source["expenses"])
    groups: dict[int, list[dict[str, Any]]] = {}
    for income in source.get("incomes", []):
        if income["base_type"] == "expense_amount":
            expense = expenses[str(income["expense_ref"])]
            groups.setdefault(id(expense), []).append(income)
    for expense in source["expenses"]:
        linked = groups.get(id(expense), [])
        if not linked:
            continue
        if expense["calc_type"] == "amount" or (
            expense.get("min") is not None and expense.get("min") == expense.get("max")
        ):
            _validate_fixed_expense(expense, linked)
        elif not _can_fund_linked_incomes(expense, linked):
            raise MonetizationValidation(
                "Сумма связанных доходов превышает расход при любой допустимой сумме"
            )


def _can_fund_linked_incomes(
    expense: dict[str, Any], linked: list[dict[str, Any]]
) -> bool:
    """Prove feasibility over the entire attainable, unrounded expense range.

    Positive percentage expenses attain every amount between their min/max.
    Each clipped income is continuous and piecewise affine in that amount.
    Therefore income minus expense reaches its minimum at a boundary or a
    clipping breakpoint, or decreases on the final unbounded interval.
    Fractions keep these intersections exact even for repeating quotients.
    Deal calculation still checks actual amounts and cent rounding.
    """
    lower = Fraction(expense["min"]) if expense.get("min") is not None else Fraction(0)
    upper = Fraction(expense["max"]) if expense.get("max") is not None else None
    boundaries = {lower}
    if upper is not None:
        # Every clipped income is nondecreasing. Even their rounded lower
        # bounds must fit the largest rounded expense attainable in this range.
        minimum_rounded_income = sum(
            floor(_exact_income(income, lower) * 100 + Fraction(1, 2)) for income in linked
        )
        if minimum_rounded_income > floor(upper * 100 + Fraction(1, 2)):
            return False
        boundaries.add(upper)
    for income in linked:
        if income["calc_type"] != "percent":
            continue
        share = Fraction(income["value"]) / 100
        for field in ("min", "max"):
            if income.get(field) is not None:
                boundary = Fraction(income[field]) / share
                if boundary >= lower and (upper is None or boundary <= upper):
                    boundaries.add(boundary)

    def surplus(available: Fraction) -> Fraction:
        return (
            sum(
                (_exact_income(income, available) for income in linked),
                Fraction(0),
            )
            - available
        )

    # Zero is only an unattainable limit, never a feasible expense.
    if any(amount > 0 and surplus(amount) <= 0 for amount in boundaries):
        return True
    if upper is not None:
        return False
    tail_slope = (
        sum(
            (
                Fraction(income["value"]) / 100
                for income in linked
                if income["calc_type"] == "percent" and income.get("max") is None
            ),
            Fraction(0),
        )
        - 1
    )
    return tail_slope < 0 or (tail_slope == 0 and surplus(max(boundaries)) <= 0)


def _exact_income(row: dict[str, Any], available: Fraction) -> Fraction:
    amount = Fraction(row["value"])
    if row["calc_type"] == "percent":
        amount = available * amount / 100
    if row.get("min") is not None:
        amount = max(amount, Fraction(row["min"]))
    if row.get("max") is not None:
        amount = min(amount, Fraction(row["max"]))
    return amount


def _validate_fixed_expense(
    expense: dict[str, Any], linked: list[dict[str, Any]]
) -> None:
    _, available, _ = _compute(expense, Decimal("0"))
    values = [_compute(income, available)[1] for income in linked]
    if sum(values, Decimal("0")) > available:
        raise MonetizationValidation(
            "Сумма связанных доходов превышает фиксированный расход"
        )
    rounded = sum(
        (value.quantize(MONEY_STEP, rounding=ROUND_HALF_UP) for value in values),
        Decimal("0"),
    )
    if rounded > available.quantize(MONEY_STEP, rounding=ROUND_HALF_UP):
        raise MonetizationValidation(
            "После округления сумма связанных доходов превышает фиксированный расход"
        )


def _validate_local_ids(source: dict[str, Any]) -> None:
    seen = set()
    for row in [*source["expenses"], *source.get("incomes", [])]:
        local_id = row.get("local_id")
        if local_id is None:
            continue
        if not isinstance(local_id, str) or not local_id.strip() or local_id in seen:
            raise MonetizationValidation(
                "Идентификаторы строк в блоке должны быть непустыми и уникальными"
            )
        seen.add(local_id)
