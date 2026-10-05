"""Accounting-report queries and handlers.

TTL-cached read flow:
    - fresh 'success' cache → return aggregated data from normalized tables
    - fresh 'not_found' cache → raise AccountingDataNotFoundError
    - stale / missing / failed → call provider, persist metadata + rows, return

The provider may be unavailable — if we have any cached data we fall back
to it rather than exposing the outage to the user.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from sqlalchemy.ext.asyncio import AsyncSession

from domain.errors import (
    AccountingDataNotFoundError,
    AccountingProviderUnavailableError,
)
from domain.services.accounting_metrics import compute_ratios
from domain.services.accounting_provider import AccountingProvider
from infrastructure.repositories import (
    accounting_report_repository as row_repo,
)
from infrastructure.repositories import (
    accounting_repository as meta_repo,
)
from infrastructure.settings import settings


@dataclass
class GetAccountingReportQuery:
    inn: str
    force_refresh: bool = False


def _rows_to_accounting_row(
    rows: list[dict[str, Any]], include_before_previous: bool = False
) -> list[dict[str, Any]]:
    """Normalize row-level DB records into {code, name, values} dicts."""
    aggregated: dict[str, dict[str, Any]] = {}
    for row in rows:
        code = row["code"]
        year = str(row["year"])
        entry = aggregated.setdefault(
            code, {"code": code, "name": row.get("name") or code, "values": {}}
        )
        entry["values"][year] = row.get("amount")
        if row.get("amount_prev") is not None:
            prev_year = str(row["year"] - 1)
            if prev_year not in entry["values"]:
                entry["values"][prev_year] = row["amount_prev"]
        if include_before_previous and row.get("amount_before_prev") is not None:
            before_prev_year = str(row["year"] - 2)
            if before_prev_year not in entry["values"]:
                entry["values"][before_prev_year] = row["amount_before_prev"]
    return list(aggregated.values())


async def _aggregate_report(
    session: AsyncSession, inn: str, meta: dict[str, Any]
) -> dict[str, Any]:
    """Aggregate metadata + normalized rows into the legacy response shape."""
    bs_rows = await row_repo.get_balance_sheet(session, inn)
    fr_rows = await row_repo.get_financial_result(session, inn)
    cf_rows = await row_repo.get_cash_flow(session, inn)
    cc_rows = await row_repo.get_capital_changes(session, inn)
    nds_rows = await row_repo.get_nds_declaration(session, inn)

    result = dict(meta)
    result["balance_sheet"] = _rows_to_accounting_row(bs_rows, include_before_previous=True)
    result["financial_result"] = _rows_to_accounting_row(fr_rows)
    result["cash_flow"] = _rows_to_accounting_row(cf_rows)
    result["capital_change"] = _rows_to_accounting_row(cc_rows)
    result["nds_declaration"] = _rows_to_accounting_row(nds_rows)

    # Recompute period_years from actual row data so that previously persisted
    # years remain selectable after a provider refresh that only returned the
    # latest year (parser-api sometimes returns a single report).
    all_years: set[int] = set()
    for rows in (bs_rows, fr_rows, cf_rows, cc_rows, nds_rows):
        for row in rows:
            year = row.get("year")
            if isinstance(year, int):
                all_years.add(year)
    result["period_years"] = sorted(all_years, reverse=True)

    return result


async def handle_get_accounting_report(
    query: GetAccountingReportQuery,
    session: AsyncSession,
    provider: AccountingProvider,
) -> dict[str, Any]:
    cached = await meta_repo.get_by_inn(session, query.inn)
    if (
        cached
        and not query.force_refresh
        and _is_fresh(cached)
    ):
        if cached["fetch_status"] == "success":
            aggregated = await _aggregate_report(session, query.inn, cached)
            return _with_cache_flag(aggregated, cached=True)
        if cached["fetch_status"] == "not_found":
            raise AccountingDataNotFoundError()
        # 'failed' or unexpected — fall through to refetch

    try:
        report = await provider.fetch_report(query.inn)
    except AccountingProviderUnavailableError as exc:
        if cached and cached.get("fetch_status") == "success":
            aggregated = await _aggregate_report(session, query.inn, cached)
            return _with_cache_flag(aggregated, cached=True, stale=True)
        await meta_repo.mark_failed(
            session,
            query.inn,
            provider_name=settings.accounting_provider_name,
            error_message=str(exc),
        )
        raise

    if report is None:
        if cached and cached.get("fetch_status") == "success":
            aggregated = await _aggregate_report(session, query.inn, cached)
            return _with_cache_flag(aggregated, cached=True, stale=True)
        await meta_repo.mark_not_found(
            session,
            query.inn,
            provider_name=settings.accounting_provider_name,
        )
        raise AccountingDataNotFoundError()

    # Save metadata (no JSONB forms)
    saved = await meta_repo.upsert_metadata(
        session,
        inn=report.inn,
        provider_name=settings.accounting_provider_name,
        period_years=list(report.period_years),
        organization=asdict(report.organization),
        audit_report=(
            asdict(report.audit_report) if report.audit_report else None
        ),
        clarification_url=report.clarification_url,
        year_files=[asdict(f) for f in report.year_files],
        computed_ratios=[asdict(r) for r in compute_ratios(report)],
    )

    # Save normalized rows
    await _save_provider_rows(session, report)

    aggregated = await _aggregate_report(session, query.inn, saved)
    return _with_cache_flag(aggregated, cached=False)


async def _save_provider_rows(
    session: AsyncSession, report: Any
) -> None:
    """Persist provider report rows into normalized tables."""
    inn = report.inn
    if not report.period_years:
        return
    period = 34

    for year in report.period_years:
        y = str(year)

        if report.balance_sheet:
            bs_data = [
                {
                    "line_code": r.code,
                    "line_name": r.name,
                    "amount": r.values.get(y),
                    "amount_prev": None,
                    "amount_before_prev": None,
                }
                for r in report.balance_sheet
            ]
            await row_repo.save_balance_sheet(
                session, bs_data, inn, year, period,
                source_type="api_fns",
            )

        if report.financial_result:
            fr_data = [
                {
                    "line_code": r.code,
                    "line_name": r.name,
                    "amount": r.values.get(y),
                    "amount_prev": None,
                }
                for r in report.financial_result
            ]
            await row_repo.save_financial_result(
                session, fr_data, inn, year, period,
                source_type="api_fns",
            )

        if report.cash_flow:
            cf_data = [
                {
                    "line_code": r.code,
                    "line_name": r.name,
                    "amount": r.values.get(y),
                    "amount_prev": None,
                }
                for r in report.cash_flow
            ]
            await row_repo.save_cash_flow(
                session, cf_data, inn, year, period,
                source_type="api_fns",
            )

        if report.capital_change:
            cc_data = [
                {
                    "line_code": r.code,
                    "line_name": r.name,
                    "amount": r.values.get(y),
                    "component_code": None,
                    "component_name": None,
                }
                for r in report.capital_change
            ]
            await row_repo.save_capital_changes(
                session, cc_data, inn, year, period,
                source_type="api_fns",
            )


def _is_fresh(cached: dict[str, Any]) -> bool:
    last_fetch_raw = cached.get("last_fetch_at")
    if not last_fetch_raw:
        return False
    try:
        last_fetch = datetime.fromisoformat(str(last_fetch_raw))
    except ValueError:
        return False
    if last_fetch.tzinfo is None:
        last_fetch = last_fetch.replace(tzinfo=UTC)
    return datetime.now(UTC) - last_fetch < timedelta(
        days=settings.accounting_cache_ttl_days
    )


def _with_cache_flag(
    record: dict[str, Any], *, cached: bool, stale: bool = False
) -> dict[str, Any]:
    enriched = dict(record)
    enriched["cached"] = cached
    enriched["stale"] = stale
    return enriched


async def get_accounting_history(
    session: AsyncSession, inn: str
) -> dict[str, list[dict[str, Any]]]:
    """Return raw history rows for an INN (used by presentation layer)."""
    return cast(
        "dict[str, list[dict[str, Any]]]",
        await row_repo.get_history(session, inn),
    )
