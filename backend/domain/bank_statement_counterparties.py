"""Existing bank analytics ranking and its questionnaire projection."""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import Any

_ZERO = Decimal("0")
_SELF_TRANSFER_NAME = "Свои счета (переводы)"


def _amount(row: dict[str, Any]) -> Decimal:
    value = row.get("amount") or _ZERO
    return value if isinstance(value, Decimal) else Decimal(str(value))


def two_year_floor(today: date) -> date:
    try:
        return today.replace(year=today.year - 2)
    except ValueError:
        return today.replace(year=today.year - 2, day=28)


def top_counterparties(transactions: list[dict], direction: str) -> list[dict]:
    grouped: dict[tuple[str, str | None, bool], Decimal] = defaultdict(lambda: _ZERO)
    for row in transactions:
        if row["direction"] != direction:
            continue
        is_self = bool(row.get("is_self_transfer"))
        name = _SELF_TRANSFER_NAME if is_self else row.get("counterparty_name") or "Без названия"
        inn = row.get("counterparty_inn")
        grouped[(name, inn, is_self)] += _amount(row)
    return [
        {
            "display_name": name,
            "inn": inn,
            "amount": amount,
            "is_self_transfer": is_self,
        }
        for (name, inn, is_self), amount in sorted(
            grouped.items(), key=lambda item: item[1], reverse=True
        )[:10]
    ]


def questionnaire_counterparties(
    transactions: list[dict[str, Any]], *, today: date
) -> list[dict[str, str]]:
    """Use the existing top-client/supplier ranking, retaining known identity only."""
    floor = two_year_floor(today)
    normalized = []
    for row in transactions:
        document_date = row.get("document_date")
        name = " ".join(str(row.get("counterparty_name") or "").split())
        inn = "".join(ch for ch in str(row.get("counterparty_inn") or "") if ch.isdigit())
        if (
            not isinstance(document_date, date) or document_date < floor
            or row.get("is_self_transfer") or not name or len(inn) not in {10, 12}
        ):
            continue
        normalized.append({**row, "counterparty_name": name, "counterparty_inn": inn})
    ranked = top_counterparties(normalized, "income") + top_counterparties(normalized, "expense")
    by_inn: dict[str, dict[str, str]] = {}
    for row in ranked:
        by_inn.setdefault(row["inn"], {"name": row["display_name"], "inn": row["inn"]})
    return list(by_inn.values())
