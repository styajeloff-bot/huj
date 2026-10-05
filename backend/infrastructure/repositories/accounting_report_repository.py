"""Repository for normalized accounting report tables (row-level upserts and reads)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.models.accounting_normalized import (
    BalanceSheet,
    CapitalChanges,
    CashFlow,
    FinancialResult,
    NDSDeclaration,
    NDSTaxRate,
)
from infrastructure.repository_timing import timed_repository


def _now() -> datetime:
    return datetime.now(UTC)

def _dedupe_by_line_code(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Remove duplicate line_code rows (keep last occurrence)."""
    seen: dict[str, dict[str, Any]] = {}
    for row in rows:
        seen[row["line_code"]] = row
    return list(seen.values())

def _dedupe_by_line_and_component(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Remove duplicate (line_code, component_code) rows (keep last)."""
    seen: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = f"{row['line_code']}::{row.get('component_code', '')}"
        seen[key] = row
    return list(seen.values())

@timed_repository
async def save_balance_sheet(
    session: AsyncSession,
    data: list[dict[str, Any]],
    inn: str,
    year: int,
    period: int,
    *,
    source_type: str = "xml_file",
) -> None:
    """Upsert balance-sheet rows for (inn, year, period, source_type)."""
    if not data:
        return

    data = _dedupe_by_line_code(data)

    values = [
        {
            "company_inn": inn,
            "report_year": year,
            "period_code": period,
            "line_code": row["line_code"],
            "company_kpp": row.get("company_kpp"),
            "company_name": row.get("company_name"),
            "period_name": row.get("period_name"),
            "line_name": row.get("line_name"),
            "okei_code": row.get("okei_code"),
            "amount": row.get("amount"),
            "amount_prev": row.get("amount_prev"),
            "amount_before_prev": row.get("amount_before_prev"),
            "source_type": source_type,
            "xml_raw": row.get("xml_raw"),
            "is_active": True,
            "superseded_by": None,
            "updated_at": _now(),
        }
        for row in data
    ]

    stmt = pg_insert(BalanceSheet).values(values)
    stmt = stmt.on_conflict_do_update(
        index_elements=["company_inn", "report_year", "period_code", "line_code", "source_type"],
        set_={
            "amount": stmt.excluded.amount,
            "amount_prev": stmt.excluded.amount_prev,
            "amount_before_prev": stmt.excluded.amount_before_prev,
            "company_name": stmt.excluded.company_name,
            "company_kpp": stmt.excluded.company_kpp,
            "okei_code": stmt.excluded.okei_code,
            "line_name": stmt.excluded.line_name,
            "period_name": stmt.excluded.period_name,
            "xml_raw": stmt.excluded.xml_raw,
            "is_active": True,
            "updated_at": _now(),
            "load_date": _now(),
            "superseded_by": None,
        },
    )
    await session.execute(stmt)
    await session.flush()

@timed_repository
async def save_financial_result(
    session: AsyncSession,
    data: list[dict[str, Any]],
    inn: str,
    year: int,
    period: int,
    *,
    source_type: str = "xml_file",
) -> None:
    """Upsert financial-result rows for (inn, year, period, source_type)."""
    if not data:
        return

    data = _dedupe_by_line_code(data)

    values = [
        {
            "company_inn": inn,
            "report_year": year,
            "period_code": period,
            "line_code": row["line_code"],
            "company_kpp": row.get("company_kpp"),
            "company_name": row.get("company_name"),
            "period_name": row.get("period_name"),
            "line_name": row.get("line_name"),
            "okei_code": row.get("okei_code"),
            "amount": row.get("amount"),
            "amount_prev": row.get("amount_prev"),
            "source_type": source_type,
            "xml_raw": row.get("xml_raw"),
            "is_active": True,
            "superseded_by": None,
            "updated_at": _now(),
        }
        for row in data
    ]

    stmt = pg_insert(FinancialResult).values(values)
    stmt = stmt.on_conflict_do_update(
        index_elements=["company_inn", "report_year", "period_code", "line_code", "source_type"],
        set_={
            "amount": stmt.excluded.amount,
            "amount_prev": stmt.excluded.amount_prev,
            "company_name": stmt.excluded.company_name,
            "company_kpp": stmt.excluded.company_kpp,
            "okei_code": stmt.excluded.okei_code,
            "line_name": stmt.excluded.line_name,
            "period_name": stmt.excluded.period_name,
            "xml_raw": stmt.excluded.xml_raw,
            "is_active": True,
            "updated_at": _now(),
            "load_date": _now(),
            "superseded_by": None,
        },
    )
    await session.execute(stmt)
    await session.flush()

@timed_repository
async def save_cash_flow(
    session: AsyncSession,
    data: list[dict[str, Any]],
    inn: str,
    year: int,
    period: int,
    *,
    source_type: str = "xml_file",
) -> None:
    """Upsert cash-flow rows for (inn, year, period, source_type)."""
    if not data:
        return

    data = _dedupe_by_line_code(data)

    values = [
        {
            "company_inn": inn,
            "report_year": year,
            "period_code": period,
            "line_code": row["line_code"],
            "company_kpp": row.get("company_kpp"),
            "company_name": row.get("company_name"),
            "period_name": row.get("period_name"),
            "line_name": row.get("line_name"),
            "okei_code": row.get("okei_code"),
            "amount": row.get("amount"),
            "amount_prev": row.get("amount_prev"),
            "source_type": source_type,
            "xml_raw": row.get("xml_raw"),
            "is_active": True,
            "superseded_by": None,
            "updated_at": _now(),
        }
        for row in data
    ]

    stmt = pg_insert(CashFlow).values(values)
    stmt = stmt.on_conflict_do_update(
        index_elements=["company_inn", "report_year", "period_code", "line_code", "source_type"],
        set_={
            "amount": stmt.excluded.amount,
            "amount_prev": stmt.excluded.amount_prev,
            "company_name": stmt.excluded.company_name,
            "company_kpp": stmt.excluded.company_kpp,
            "okei_code": stmt.excluded.okei_code,
            "line_name": stmt.excluded.line_name,
            "period_name": stmt.excluded.period_name,
            "xml_raw": stmt.excluded.xml_raw,
            "is_active": True,
            "updated_at": _now(),
            "load_date": _now(),
            "superseded_by": None,
        },
    )
    await session.execute(stmt)
    await session.flush()

@timed_repository
async def save_capital_changes(
    session: AsyncSession,
    data: list[dict[str, Any]],
    inn: str,
    year: int,
    period: int,
    *,
    source_type: str = "xml_file",
) -> None:
    """Upsert capital-changes rows for (inn, year, period, source_type)."""
    if not data:
        return

    data = _dedupe_by_line_and_component(data)

    values = [
        {
            "company_inn": inn,
            "report_year": year,
            "period_code": period,
            "line_code": row["line_code"],
            "component_code": row.get("component_code"),
            "component_name": row.get("component_name"),
            "company_kpp": row.get("company_kpp"),
            "company_name": row.get("company_name"),
            "period_name": row.get("period_name"),
            "line_name": row.get("line_name"),
            "okei_code": row.get("okei_code"),
            "amount": row.get("amount"),
            "amount_prev": row.get("amount_prev"),
            "source_type": source_type,
            "xml_raw": row.get("xml_raw"),
            "is_active": True,
            "superseded_by": None,
            "updated_at": _now(),
        }
        for row in data
    ]

    stmt = pg_insert(CapitalChanges).values(values)
    stmt = stmt.on_conflict_do_update(
        index_elements=["company_inn", "report_year", "period_code", "line_code", "component_code", "source_type"],
        set_={
            "amount": stmt.excluded.amount,
            "amount_prev": stmt.excluded.amount_prev,
            "component_code": stmt.excluded.component_code,
            "component_name": stmt.excluded.component_name,
            "company_name": stmt.excluded.company_name,
            "company_kpp": stmt.excluded.company_kpp,
            "okei_code": stmt.excluded.okei_code,
            "line_name": stmt.excluded.line_name,
            "period_name": stmt.excluded.period_name,
            "xml_raw": stmt.excluded.xml_raw,
            "is_active": True,
            "updated_at": _now(),
            "load_date": _now(),
            "superseded_by": None,
        },
    )
    await session.execute(stmt)
    await session.flush()

# ── Read methods ─────────────────────────────────────────────

@timed_repository
async def get_balance_sheet(
    session: AsyncSession,
    inn: str,
) -> list[dict[str, Any]]:
    """Return active balance-sheet rows for INN."""
    result = await session.execute(
        sa.select(BalanceSheet)
        .where(BalanceSheet.company_inn == inn)
        .where(BalanceSheet.is_active.is_(True))
        .order_by(BalanceSheet.line_code)
    )
    return [
        {
            "code": row.line_code,
            "name": row.line_name,
            "year": row.report_year,
            "amount": row.amount,
            "amount_prev": row.amount_prev,
            "amount_before_prev": row.amount_before_prev,
            "source_type": row.source_type,
        }
        for row in result.scalars().all()
    ]

@timed_repository
async def get_financial_result(
    session: AsyncSession,
    inn: str,
) -> list[dict[str, Any]]:
    """Return active financial-result rows for INN."""
    result = await session.execute(
        sa.select(FinancialResult)
        .where(FinancialResult.company_inn == inn)
        .where(FinancialResult.is_active.is_(True))
        .order_by(FinancialResult.line_code)
    )
    return [
        {
            "code": row.line_code,
            "name": row.line_name,
            "year": row.report_year,
            "amount": row.amount,
            "amount_prev": row.amount_prev,
            "source_type": row.source_type,
        }
        for row in result.scalars().all()
    ]

@timed_repository
async def get_cash_flow(
    session: AsyncSession,
    inn: str,
) -> list[dict[str, Any]]:
    """Return active cash-flow rows for INN."""
    result = await session.execute(
        sa.select(CashFlow)
        .where(CashFlow.company_inn == inn)
        .where(CashFlow.is_active.is_(True))
        .order_by(CashFlow.line_code)
    )
    return [
        {
            "code": row.line_code,
            "name": row.line_name,
            "year": row.report_year,
            "amount": row.amount,
            "amount_prev": row.amount_prev,
            "source_type": row.source_type,
        }
        for row in result.scalars().all()
    ]

@timed_repository
async def get_capital_changes(
    session: AsyncSession,
    inn: str,
) -> list[dict[str, Any]]:
    """Return active capital-changes rows for INN."""
    result = await session.execute(
        sa.select(CapitalChanges)
        .where(CapitalChanges.company_inn == inn)
        .where(CapitalChanges.is_active.is_(True))
        .order_by(CapitalChanges.line_code)
    )
    return [
        {
            "code": row.line_code,
            "name": row.line_name,
            "year": row.report_year,
            "amount": row.amount,
            "amount_prev": row.amount_prev,
            "source_type": row.source_type,
        }
        for row in result.scalars().all()
    ]

# ── History ──────────────────────────────────────────────────

@timed_repository
async def get_history(
    session: AsyncSession,
    inn: str,
) -> dict[str, list[dict[str, Any]]]:
    """Return all versions (active and archived) with upload dates.

    Result shape:
        {
            "balance_sheet": [...],
            "financial_result": [...],
            "cash_flow": [...],
            "capital_changes": [...],
        }
    Each row dict includes ``is_active``, ``load_date`` and
    ``updated_at`` so callers can reconstruct the timeline.
    """
    history: dict[str, list[dict[str, Any]]] = {
        "balance_sheet": [],
        "financial_result": [],
        "cash_flow": [],
        "capital_changes": [],
    }

    # Balance sheet
    bs_result = await session.execute(
        sa.select(BalanceSheet)
        .where(BalanceSheet.company_inn == inn)
        .order_by(
            BalanceSheet.report_year.desc(),
            BalanceSheet.period_code.desc(),
            BalanceSheet.line_code,
            BalanceSheet.load_date.desc(),
        )
    )
    for bs_row in bs_result.scalars().all():
        history["balance_sheet"].append(
            {
                "code": bs_row.line_code,
                "name": bs_row.line_name,
                "year": bs_row.report_year,
                "period": bs_row.period_code,
                "amount": bs_row.amount,
                "amount_prev": bs_row.amount_prev,
                "amount_before_prev": bs_row.amount_before_prev,
                "source_type": bs_row.source_type,
                "is_active": bs_row.is_active,
                "load_date": bs_row.load_date,
                "updated_at": bs_row.updated_at,
            }
        )

    # Financial result
    fr_result = await session.execute(
        sa.select(FinancialResult)
        .where(FinancialResult.company_inn == inn)
        .order_by(
            FinancialResult.report_year.desc(),
            FinancialResult.period_code.desc(),
            FinancialResult.line_code,
            FinancialResult.load_date.desc(),
        )
    )
    for fr_row in fr_result.scalars().all():
        history["financial_result"].append(
            {
                "code": fr_row.line_code,
                "name": fr_row.line_name,
                "year": fr_row.report_year,
                "period": fr_row.period_code,
                "amount": fr_row.amount,
                "amount_prev": fr_row.amount_prev,
                "source_type": fr_row.source_type,
                "is_active": fr_row.is_active,
                "load_date": fr_row.load_date,
                "updated_at": fr_row.updated_at,
            }
        )

    # Cash flow
    cf_result = await session.execute(
        sa.select(CashFlow)
        .where(CashFlow.company_inn == inn)
        .order_by(
            CashFlow.report_year.desc(),
            CashFlow.period_code.desc(),
            CashFlow.line_code,
            CashFlow.load_date.desc(),
        )
    )
    for cf_row in cf_result.scalars().all():
        history["cash_flow"].append(
            {
                "code": cf_row.line_code,
                "name": cf_row.line_name,
                "year": cf_row.report_year,
                "period": cf_row.period_code,
                "amount": cf_row.amount,
                "amount_prev": cf_row.amount_prev,
                "source_type": cf_row.source_type,
                "is_active": cf_row.is_active,
                "load_date": cf_row.load_date,
                "updated_at": cf_row.updated_at,
            }
        )

    # Capital changes
    cc_result = await session.execute(
        sa.select(CapitalChanges)
        .where(CapitalChanges.company_inn == inn)
        .order_by(
            CapitalChanges.report_year.desc(),
            CapitalChanges.period_code.desc(),
            CapitalChanges.line_code,
            CapitalChanges.component_code,
            CapitalChanges.load_date.desc(),
        )
    )
    for cc_row in cc_result.scalars().all():
        history["capital_changes"].append(
            {
                "code": cc_row.line_code,
                "name": cc_row.line_name,
                "component_code": cc_row.component_code,
                "component_name": cc_row.component_name,
                "year": cc_row.report_year,
                "period": cc_row.period_code,
                "amount": cc_row.amount,
                "amount_prev": cc_row.amount_prev,
                "source_type": cc_row.source_type,
                "is_active": cc_row.is_active,
                "load_date": cc_row.load_date,
                "updated_at": cc_row.updated_at,
            }
        )

    return history

@timed_repository
async def save_nds_declaration(
    session: AsyncSession,
    data: list[dict[str, Any]],
    inn: str,
    year: int,
    period: int,
    *,
    source_type: str = "xml_file",
) -> None:
    """Upsert NDS declaration rows."""
    if not data:
        return
    data = _dedupe_by_line_code(data)

    # Map XML tag names (line_code) to tax_rate_id references
    tags = [row["line_code"] for row in data if row.get("line_code")]
    tag_to_id: dict[str, int] = {}
    if tags:
        rate_result = await session.execute(
            sa.select(NDSTaxRate.id, NDSTaxRate.xml_tag)
            .where(NDSTaxRate.xml_tag.in_(tags))
        )
        tag_to_id = {tag: id_ for id_, tag in rate_result.all()}

    values = [
        {
            "company_inn": inn,
            "report_year": year,
            "period_code": period,
            "tax_rate_id": tag_to_id[row["line_code"]],
            "company_kpp": row.get("company_kpp"),
            "company_name": row.get("company_name"),
            "period_name": row.get("period_name"),
            "tax_base": row.get("tax_base"),
            "tax_amount": row.get("tax_amount"),
            "total_tax_payable": row.get("total_tax_payable"),
            "total_deductions": row.get("total_deductions"),
            "total_recovered": row.get("total_recovered"),
            "source_type": source_type,
            "is_active": True,
            "superseded_by": None,
            "updated_at": _now(),
        }
        for row in data
        if row.get("line_code") in tag_to_id
    ]

    if not values:
        return

    stmt = pg_insert(NDSDeclaration).values(values)
    stmt = stmt.on_conflict_do_update(
        index_elements=["company_inn", "report_year", "period_code", "tax_rate_id", "source_type"],
        set_={
            "tax_base": stmt.excluded.tax_base,
            "tax_amount": stmt.excluded.tax_amount,
            "total_tax_payable": stmt.excluded.total_tax_payable,
            "total_deductions": stmt.excluded.total_deductions,
            "total_recovered": stmt.excluded.total_recovered,
            "company_name": stmt.excluded.company_name,
            "company_kpp": stmt.excluded.company_kpp,
            "period_name": stmt.excluded.period_name,
            "is_active": True,
            "updated_at": _now(),
            "load_date": _now(),
            "superseded_by": None,
        },
    )
    await session.execute(stmt)
    await session.flush()

@timed_repository
async def get_nds_declaration(session: AsyncSession, inn: str) -> list[dict[str, Any]]:
    """Return active NDS declaration rows for INN."""
    result = await session.execute(
        sa.select(NDSDeclaration, NDSTaxRate)
        .join(NDSTaxRate, NDSDeclaration.tax_rate_id == NDSTaxRate.id)
        .where(NDSDeclaration.company_inn == inn)
        .where(NDSDeclaration.is_active.is_(True))
        .order_by(NDSDeclaration.tax_rate_id)
    )
    return [
        {
            "code": rate.xml_tag,
            "name": rate.tax_base_description,
            "year": decl.report_year,
            "amount": decl.tax_base,
            "tax_amount": decl.tax_amount,
            "total_tax_payable": decl.total_tax_payable,
            "total_deductions": decl.total_deductions,
            "total_recovered": decl.total_recovered,
            "source_type": decl.source_type,
        }
        for decl, rate in result.all()
    ]
