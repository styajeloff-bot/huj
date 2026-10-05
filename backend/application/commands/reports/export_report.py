"""Export a report to CSV or Excel.

The command resolves role-scoped access through the same code path as the
individual report queries, builds a tabular projection of the chosen
report, and serializes it to CSV or xlsx bytes. The router wraps the
result in a ``StreamingResponse`` with the right headers.

Only rows are exported — a report's overview / distribution aggregates
are not re-serialized here because Excel / CSV target a flat table shape
and Express's original export did the same (``reportData.applications ||
reportData.overview``).
"""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.queries.reports.get_dealer_report import (
    GetDealerReportQuery,
    handle_get_dealer_report,
)
from application.queries.reports.get_distributor_report import (
    GetDistributorReportQuery,
    handle_get_distributor_report,
)
from application.queries.reports.get_leasing_company_report import (
    GetLeasingCompanyReportQuery,
    handle_get_leasing_company_report,
)
from domain.errors import (
    InvalidDateRangeError,
    InvalidExportFormatError,
    InvalidReportTypeError,
    ReportsAccessDeniedError,
)
from infrastructure.repositories import reporting_repository as repo
from infrastructure.services.excel_io import write_workbook

_REPORT_TYPES: frozenset[str] = frozenset(
    {"admin", "carcraft_employee", "dealer", "leasing_company", "distributor"}
)
_EXPORT_FORMATS: frozenset[str] = frozenset({"csv", "excel"})
_EXCEL_MIME = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)
_CSV_MIME = "text/csv; charset=utf-8"

# Safety threshold — log a warning when the export hits this many rows.
_LARGE_EXPORT_WARN_ROWS = 10_000


@dataclass
class ExportReportCommand:
    actor_id: UUID
    actor_role: str
    actor_company_id: UUID | None
    report_type: str
    export_format: str
    date_from: datetime | None = None
    date_to: datetime | None = None
    filters: dict[str, Any] | None = None


@dataclass
class ExportReportResult:
    content: bytes
    filename: str
    mime_type: str
    row_count: int


def _ensure_range(date_from: datetime | None, date_to: datetime | None) -> None:
    for value in (date_from, date_to):
        if value is not None and value.tzinfo is None:
            raise InvalidDateRangeError(
                "Даты должны быть в формате ISO-8601 с указанием таймзоны"
            )
    if date_from is not None and date_to is not None and date_from > date_to:
        raise InvalidDateRangeError(
            "Начало периода не может быть позже конца"
        )


def _normalize_report_type(value: str) -> str:
    lowered = (value or "").strip().lower()
    if lowered == "carcraft_employee":
        lowered = "admin"
    if lowered not in _REPORT_TYPES:
        raise InvalidReportTypeError(value)
    # Normalize alias
    return "admin" if lowered == "carcraft_employee" else lowered


def _normalize_format(value: str) -> str:
    lowered = (value or "").strip().lower()
    if lowered not in _EXPORT_FORMATS:
        raise InvalidExportFormatError(value)
    return lowered


def _sanitize_filename(name: str) -> str:
    safe_chars: list[str] = []
    for ch in name:
        if ch.isalnum() or ch in {"_", "-", "."}:
            safe_chars.append(ch)
        else:
            safe_chars.append("_")
    sanitized = "".join(safe_chars)
    while ".." in sanitized:
        sanitized = sanitized.replace("..", ".")
    return sanitized[:200] or "report.csv"


def _csv_escape(value: Any) -> str:
    if value is None:
        return ""
    text = str(value)
    formula_chars = ("=", "+", "-", "@", "\t", "\r")
    if text.startswith(formula_chars):
        text = "'" + text
    return text


def _rows_to_csv(headers: list[str], rows: list[dict[str, Any]]) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer, quoting=csv.QUOTE_MINIMAL, lineterminator="\r\n")
    writer.writerow(headers)
    for row in rows:
        writer.writerow([_csv_escape(row.get(h)) for h in headers])
    return buffer.getvalue().encode("utf-8-sig")


async def _rows_to_excel(
    headers: list[str], rows: list[dict[str, Any]]
) -> bytes:
    body = [
        [row.get(h) for h in headers]
        for row in rows
    ]
    return await write_workbook(headers, body, sheet_name="Report")


_DEALER_HEADERS = [
    "id",
    "status",
    "total_amount",
    "company_id",
    "name",
    "email",
    "created_at",
    "updated_at",
]
_LC_HEADERS = [
    "id",
    "status",
    "total_amount",
    "company_id",
    "name",
    "email",
    "created_at",
    "updated_at",
]
_DISTRIBUTOR_HEADERS = [
    "id",
    "status",
    "total_amount",
    "company_id",
    "name",
    "email",
    "created_at",
    "updated_at",
]
_ADMIN_HEADERS = [
    "dealer_id",
    "dealer_name",
    "dealer_email",
    "applications_count",
    "approved_count",
    "total_amount",
    "approval_rate",
]


async def _collect_rows(
    report_type: str,
    *,
    cmd: ExportReportCommand,
    session: AsyncSession,
) -> tuple[list[str], list[dict[str, Any]]]:
    if report_type == "dealer":
        result = await handle_get_dealer_report(
            GetDealerReportQuery(
                actor_id=cmd.actor_id,
                actor_role=cmd.actor_role,
                dealer_id=_extract_filter(cmd, "dealer_id"),
                date_from=cmd.date_from,
                date_to=cmd.date_to,
            ),
            session,
        )
        return _DEALER_HEADERS, list(result.get("applications") or [])
    if report_type == "leasing_company":
        result = await handle_get_leasing_company_report(
            GetLeasingCompanyReportQuery(
                actor_id=cmd.actor_id,
                actor_role=cmd.actor_role,
                actor_company_id=cmd.actor_company_id,
                leasing_company_id=_extract_filter(cmd, "leasing_company_id"),
                date_from=cmd.date_from,
                date_to=cmd.date_to,
            ),
            session,
        )
        return _LC_HEADERS, list(result.get("applications") or [])
    if report_type == "distributor":
        result = await handle_get_distributor_report(
            GetDistributorReportQuery(
                actor_id=cmd.actor_id,
                actor_role=cmd.actor_role,
                actor_company_id=cmd.actor_company_id,
                distributor_id=_extract_filter(cmd, "distributor_id"),
                date_from=cmd.date_from,
                date_to=cmd.date_to,
            ),
            session,
        )
        return _DISTRIBUTOR_HEADERS, list(result.get("applications") or [])
    if report_type == "admin":
        if cmd.actor_role != "carcraft_employee":
            raise ReportsAccessDeniedError(
                "Экспорт admin-отчёта доступен только сотрудникам Carcraft"
            )
        top = await repo.top_dealers(
            session, date_from=cmd.date_from, date_to=cmd.date_to
        )
        return _ADMIN_HEADERS, list(top)
    raise InvalidReportTypeError(report_type)


def _extract_filter(cmd: ExportReportCommand, key: str) -> UUID | None:
    if not cmd.filters:
        return None
    raw = cmd.filters.get(key)
    if raw is None:
        return None
    try:
        return UUID(str(raw))
    except (TypeError, ValueError):
        return None


async def handle_export_report(
    cmd: ExportReportCommand, session: AsyncSession
) -> ExportReportResult:
    _ensure_range(cmd.date_from, cmd.date_to)
    report_type = _normalize_report_type(cmd.report_type)
    export_format = _normalize_format(cmd.export_format)

    headers, rows = await _collect_rows(report_type, cmd=cmd, session=session)
    row_count = len(rows)

    # Stringify common non-scalar column values (datetimes / Decimals) so
    # writers don't have to special-case them.
    for row in rows:
        for key, value in list(row.items()):
            if isinstance(value, datetime):
                row[key] = value.isoformat()
            elif value is None:
                row[key] = ""
            elif isinstance(value, (list | tuple | dict | set)):
                row[key] = str(value)

    today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
    suffix = "xlsx" if export_format == "excel" else "csv"
    filename = _sanitize_filename(f"{report_type}_report_{today}.{suffix}")

    if export_format == "csv":
        content = _rows_to_csv(headers, rows)
        mime = _CSV_MIME
    else:
        content = await _rows_to_excel(headers, rows)
        mime = _EXCEL_MIME

    return ExportReportResult(
        content=content,
        filename=filename,
        mime_type=mime,
        row_count=row_count,
    )


__all__ = [
    "_LARGE_EXPORT_WARN_ROWS",
    "ExportReportCommand",
    "ExportReportResult",
    "handle_export_report",
]
