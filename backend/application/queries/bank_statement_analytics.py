"""Bank statement analytics query."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.errors import ServiceError
from domain.bank_statement_counterparties import (
    top_counterparties,
)
from domain.bank_statement_counterparties import two_year_floor as _two_year_floor
from infrastructure.repositories import bank_statement_repository as repo
from infrastructure.repositories import company_repository

_ZERO = Decimal("0")


@dataclass(frozen=True)
class GetBankStatementAnalyticsQuery:
    company_id: UUID


def _now() -> datetime:
    return datetime.now(UTC)


async def handle_get_bank_statement_analytics(
    query: GetBankStatementAnalyticsQuery,
    session: AsyncSession,
    user: dict,
) -> dict:
    await _ensure_can_read_company_analytics(query, session, user)

    source = await repo.get_company_bank_analytics_source(session, query.company_id)
    if source is None:
        raise ServiceError("Компания не найдена", 404)

    transactions = [
        row for row in source["transactions"] if row.get("document_date") is not None
    ]
    accounts = [
        {"account_number": item["account_number"], "bank_name": item["bank_name"]}
        for item in source["accounts"]
    ]
    if not transactions:
        return {
            "company": source["company"],
            "accounts": accounts,
            "period": None,
            "kpi": _empty_kpi(),
            "cashflow": [],
            "expense_structure": [],
            "top_clients": [],
            "top_suppliers": [],
            "empty": True,
        }

    earliest = min(row["document_date"] for row in transactions)
    latest = max(row["document_date"] for row in transactions)
    floor = _two_year_floor(_now().date())
    start = max(earliest, floor)
    bounded = [row for row in transactions if start <= row["document_date"] <= latest]
    external = [row for row in bounded if not row.get("is_self_transfer")]
    income = sum(
        (_amount(row) for row in external if row["direction"] == "income"), _ZERO
    )
    expense = sum(
        (_amount(row) for row in external if row["direction"] == "expense"), _ZERO
    )
    turnover = income + expense
    active_months = {
        row["document_date"].strftime("%Y-%m")
        for row in external
        if row["direction"] in {"income", "expense"} and _amount(row) != _ZERO
    }
    external_revenue = sum(
        (
            _amount(row)
            for row in external
            if row["direction"] == "income"
            and row["operation_kind"] == "Оплата покупателя"
        ),
        _ZERO,
    )
    period_imports = _imports_for_period(source["imports"], start, latest)
    opening_balance = _opening_balance(period_imports)
    closing_balance = _closing_balance(period_imports)
    if closing_balance is None:
        closing_balance = opening_balance + income - expense
    kpi = {
        "income": _float(income),
        "expense": _float(expense),
        "turnover": _float(turnover),
        "average_monthly_turnover": _float(
            turnover / Decimal(len(active_months)) if active_months else _ZERO
        ),
        "external_revenue": _float(external_revenue),
        "opening_balance": _float(opening_balance),
        "closing_balance": _float(closing_balance),
        "balance_change": _float(closing_balance - opening_balance),
    }

    return {
        "company": source["company"],
        "accounts": accounts,
        "period": {"start": start, "end": latest},
        "kpi": kpi,
        "cashflow": _cashflow(external, opening_balance),
        "expense_structure": _expense_structure(external),
        "top_clients": _top_counterparties(bounded, "income"),
        "top_suppliers": _top_counterparties(bounded, "expense"),
        "empty": False,
    }


async def _ensure_can_read_company_analytics(
    query: GetBankStatementAnalyticsQuery,
    session: AsyncSession,
    user: dict,
) -> None:
    role = str(user.get("role") or "")
    actor_company_id = _uuid_or_none(user.get("company_id"))
    if role in {"carcraft_employee", "distributor"}:
        return
    if role in {"client", "dealer"}:
        actor_user_id = _uuid_or_none(user.get("id"))
        if actor_company_id == query.company_id:
            return
        if actor_user_id is not None and await company_repository.is_user_linked_to_company(
            session,
            actor_user_id,
            query.company_id,
        ):
            return
    if role == "leasing_company":
        leasing_company_id = _uuid_or_none(user.get("leasing_company_id"))
        if leasing_company_id is not None and await repo.company_has_selected_lc_application(
            session,
            company_id=query.company_id,
            leasing_company_id=leasing_company_id,
        ):
            return
    raise ServiceError("Недостаточно прав доступа", 403)


def _uuid_or_none(value: object) -> UUID | None:
    if value is None:
        return None
    if isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except ValueError:
        return None


def _empty_kpi() -> dict[str, float]:
    return {
        "income": 0.0,
        "expense": 0.0,
        "turnover": 0.0,
        "average_monthly_turnover": 0.0,
        "external_revenue": 0.0,
        "opening_balance": 0.0,
        "closing_balance": 0.0,
        "balance_change": 0.0,
    }


def _amount(row: dict) -> Decimal:
    value = row.get("amount") or _ZERO
    return value if isinstance(value, Decimal) else Decimal(str(value))


def _float(value: Decimal | None) -> float:
    return float((value or _ZERO).quantize(Decimal("0.01")))


def _imports_for_period(imports: list[dict], start: date, end: date) -> list[dict]:
    return [
        item
        for item in imports
        if (item.get("period_end") is None or item["period_end"] >= start)
        and (item.get("period_start") is None or item["period_start"] <= end)
    ]


def _account_key(item: dict) -> str:
    return str(item.get("statement_account") or item.get("id"))


def _opening_balance(imports: list[dict]) -> Decimal:
    by_account: dict[str, Decimal] = {}
    for item in imports:
        if item.get("opening_balance") is None:
            continue
        by_account.setdefault(
            _account_key(item),
            _amount({"amount": item["opening_balance"]}),
        )
    return sum(by_account.values(), _ZERO)


def _closing_balance(imports: list[dict]) -> Decimal | None:
    by_account: dict[str, Decimal] = {}
    for item in reversed(imports):
        if item.get("closing_balance") is None:
            continue
        by_account.setdefault(
            _account_key(item),
            _amount({"amount": item["closing_balance"]}),
        )
    if not by_account:
        return None
    return sum(by_account.values(), _ZERO)


def _cashflow(transactions: list[dict], opening_balance: Decimal) -> list[dict]:
    grouped: dict[str, dict[str, Decimal]] = defaultdict(
        lambda: {"income": _ZERO, "expense": _ZERO}
    )
    for row in transactions:
        month = row["document_date"].strftime("%Y-%m")
        if row["direction"] == "income":
            grouped[month]["income"] += _amount(row)
        elif row["direction"] == "expense":
            grouped[month]["expense"] += _amount(row)

    balance = opening_balance
    out: list[dict] = []
    for month in sorted(grouped):
        income = grouped[month]["income"]
        expense = grouped[month]["expense"]
        balance += income - expense
        out.append(
            {
                "month": month,
                "income": _float(income),
                "expense": _float(expense),
                "closing_balance": _float(balance),
            }
        )
    return out


def _expense_structure(transactions: list[dict]) -> list[dict]:
    grouped: dict[str, Decimal] = defaultdict(lambda: _ZERO)
    for row in transactions:
        if row["direction"] == "expense":
            grouped[row["operation_kind"]] += _amount(row)
    total = sum(grouped.values(), _ZERO)
    if total == _ZERO:
        return []
    return [
        {
            "operation_kind": kind,
            "amount": _float(amount),
            "share": _float(amount / total * Decimal("100")),
        }
        for kind, amount in sorted(grouped.items(), key=lambda item: item[1], reverse=True)
    ]



def _top_counterparties(transactions: list[dict], direction: str) -> list[dict]:
    return [
        {**row, "amount": _float(row["amount"])}
        for row in top_counterparties(transactions, direction)
    ]
