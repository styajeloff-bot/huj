"""Parser API implementation of AccountingProvider (parser-api.com nalog-bo).

Two-hop fetch:
    1. GET /parser/nalog_bo_api/search?key=…&inn=…   → items[0].id
    2. GET /parser/nalog_bo_api/details?key=…&id=…   → full report

All amounts from the source come in thousands of roubles — we multiply
by 1000 to normalize into rubles.
"""
from __future__ import annotations

from typing import Any

import httpx

from domain.errors import AccountingProviderUnavailableError
from domain.values_accounting import (
    AccountingReport,
    AccountingRow,
    AccountingYearFile,
    AuditReport,
    OrganizationInfo,
)
from infrastructure.logging import log_event

_AMOUNT_MULTIPLIER = 1000  # тысячи рублей → рубли


class ParserApiAccountingProvider:
    """Adapter for parser-api.com nalog-bo endpoint."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        timeout_ms: int,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout_seconds = max(timeout_ms, 1000) / 1000

    async def fetch_report(self, inn: str) -> AccountingReport | None:
        if not self._api_key:
            raise AccountingProviderUnavailableError(
                "Parser API ключ не настроен (PARSER_API_KEY)"
            )

        async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
            search_payload = await self._search(client, inn)
            item = _first_item(search_payload)
            if item is None:
                log_event(
                    "info",
                    "accounting.parser.search_empty",
                    "Accounting provider found no company",
                    component="accounting",
                    dependency="parser-api",
                    operation="search",
                    result="empty",
                )
                return None

            detail_id = item.get("id")
            log_event(
                "debug",
                "accounting.parser.item_selected",
                "Accounting provider search item selected",
                component="accounting",
                dependency="parser-api",
                operation="search",
                result="selected",
            )
            if not detail_id:
                log_event(
                    "warning",
                    "accounting.parser.item_invalid",
                    "Accounting provider result has no detail identifier",
                    component="accounting",
                    dependency="parser-api",
                    operation="search",
                    result="invalid",
                )
                return None

            details_payload = await self._details(client, detail_id)
            reports = details_payload.get("reports")
            reports_count = len(reports) if isinstance(reports, list) else 0
            log_event(
                "debug",
                "accounting.parser.details_received",
                "Accounting provider details received",
                component="accounting",
                dependency="parser-api",
                operation="details",
                report_count=reports_count,
            )

        return _normalize(inn, details_payload, fallback_item=item)

    async def _search(
        self, client: httpx.AsyncClient, inn: str
    ) -> dict[str, Any]:
        url = f"{self._base_url}/parser/nalog_bo_api/search"
        return await self._get(
            client, url, {"key": self._api_key, "inn": inn}, op="search"
        )

    async def _details(
        self, client: httpx.AsyncClient, detail_id: int | str
    ) -> dict[str, Any]:
        url = f"{self._base_url}/parser/nalog_bo_api/details"
        return await self._get(
            client,
            url,
            {"key": self._api_key, "id": detail_id},
            op="details",
        )

    async def _get(
        self,
        client: httpx.AsyncClient,
        url: str,
        params: dict[str, Any],
        *,
        op: str = "get",
    ) -> dict[str, Any]:
        log_event(
            "debug",
            "accounting.parser.request_started",
            "Accounting provider request started",
            component="accounting",
            dependency="parser-api",
            operation=op,
        )
        try:
            response = await client.get(url, params=params)
        except httpx.HTTPError as exc:
            log_event(
                "warning",
                "accounting.parser.request_failed",
                "Accounting provider request failed",
                error=exc,
                component="accounting",
                dependency="parser-api",
                operation=op,
            )
            raise AccountingProviderUnavailableError() from exc

        log_event(
            "debug",
            "accounting.parser.response_received",
            "Accounting provider response received",
            component="accounting",
            dependency="parser-api",
            operation=op,
            http_status_code=response.status_code,
            response_size_bytes=len(response.content),
            response_content_type=response.headers.get("content-type", "unknown"),
        )

        if response.status_code >= 500:
            raise AccountingProviderUnavailableError()
        if response.status_code >= 400:
            raise AccountingProviderUnavailableError(
                f"Third API вернул {response.status_code}"
            )

        try:
            data = response.json()
        except ValueError as exc:
            raise AccountingProviderUnavailableError(
                "Third API вернул невалидный JSON"
            ) from exc
        if not isinstance(data, dict):
            raise AccountingProviderUnavailableError(
                "Parser API: неожиданная форма ответа"
            )
        return data


def _first_item(search_payload: dict[str, Any]) -> dict[str, Any] | None:
    """Pick the first company record out of a parser-api search response.

    parser-api uses a few different shapes across deployments/versions:
        {"success": 1, "items":        [{id, inn, ...}, ...]}
        {"success": 1, "data":         [{id, inn, ...}, ...]}
        {"success": 1, "result":       [{id, inn, ...}, ...]}
        {"success": 1, "companies":    [{id, inn, ...}, ...]}
        {"success": 1, "organization": {id, inn, ...}}
        {"success": 1, id: N, inn: …}                       # flat
    """
    for key in ("items", "data", "result", "companies", "list"):
        value = search_payload.get(key)
        if isinstance(value, list) and value and isinstance(value[0], dict):
            return value[0]
    for key in ("organization", "company", "item"):
        value = search_payload.get(key)
        if isinstance(value, dict) and (value.get("id") or value.get("inn")):
            return value
    if search_payload.get("id") and search_payload.get("inn"):
        return search_payload
    return None


def _normalize(
    inn: str,
    details: dict[str, Any],
    *,
    fallback_item: dict[str, Any],
) -> AccountingReport | None:
    organization = _parse_organization(
        inn, details.get("organization") or fallback_item
    )
    reports = details.get("reports")
    if not isinstance(reports, list) or not reports:
        return None

    reports_valid = [
        raw for raw in reports
        if isinstance(raw, dict) and _safe_int(raw.get("period")) is not None
    ]
    reports_asc = sorted(
        reports_valid, key=lambda r: _safe_int(r.get("period")) or 0
    )

    balance_sheet = _aggregate_rows(
        reports_asc, "balance", include_before_previous=True
    )
    financial_result = _aggregate_rows(
        reports_asc, "financial_result", include_before_previous=False
    )
    cash_flow = _aggregate_rows(
        reports_asc, "funds_movement", include_before_previous=False
    )
    capital_change = _aggregate_capital_change(reports_asc)

    all_years: set[int] = set()
    for rows in (balance_sheet, financial_result, cash_flow, capital_change):
        for row in rows:
            for year_key in row.values:
                parsed = _safe_int(year_key)
                if parsed is not None:
                    all_years.add(parsed)
    period_years: list[int] = sorted(all_years, reverse=True)

    latest = reports_asc[-1] if reports_asc else {}
    audit = _parse_audit(latest.get("audit_report"))
    clarification_url = _parse_clarification(latest.get("clarification"))
    year_files = _build_year_files(reports)

    return AccountingReport(
        inn=inn,
        period_years=period_years,
        organization=organization,
        balance_sheet=balance_sheet,
        financial_result=financial_result,
        cash_flow=cash_flow,
        capital_change=capital_change,
        audit_report=audit,
        clarification_url=clarification_url,
        year_files=year_files,
    )


def _build_year_files(reports: list[Any]) -> list[AccountingYearFile]:
    out: list[AccountingYearFile] = []
    for raw in reports:
        if not isinstance(raw, dict):
            continue
        year = _safe_int(raw.get("period"))
        if year is None:
            continue
        detail_id = _str_or_none(raw.get("detail_id") or raw.get("id"))
        pdf_url = _str_or_none(raw.get("url"))
        audit_raw = raw.get("audit_report") if isinstance(raw.get("audit_report"), dict) else None
        clar_raw = raw.get("clarification") if isinstance(raw.get("clarification"), dict) else None
        audit_pdf = (
            _str_or_none(audit_raw.get("file_url") or audit_raw.get("url") or audit_raw.get("pdf_url"))
            if audit_raw else None
        )
        clar_pdf = (
            _str_or_none(clar_raw.get("file_url") or clar_raw.get("url") or clar_raw.get("pdf_url"))
            if clar_raw else None
        )
        out.append(
            AccountingYearFile(
                year=year,
                detail_id=detail_id,
                pdf_url=pdf_url,
                audit_pdf_url=audit_pdf,
                clarification_pdf_url=clar_pdf,
            )
        )
    # Newest year first — matches period_years ordering.
    out.sort(key=lambda x: x.year, reverse=True)
    return out


def _parse_organization(inn: str, source: dict[str, Any]) -> OrganizationInfo:
    location = source.get("location")
    tax_authority_name: str | None = None
    tax_authority_code: str | None = None
    if isinstance(location, dict):
        tax_authority_name = _str_or_none(location.get("name"))
        tax_authority_code = _str_or_none(location.get("code"))

    address_parts = [
        source.get(key)
        for key in (
            "index",
            "region",
            "district",
            "city",
            "settlement",
            "street",
            "house",
            "building",
            "office",
        )
    ]
    address = ", ".join(str(p) for p in address_parts if p) or None

    okved2 = source.get("okved2")
    okved_str: str | None
    if isinstance(okved2, dict):
        okved_str = " ".join(
            str(v) for v in (okved2.get("code"), okved2.get("name")) if v
        )
    else:
        okved_str = str(okved2) if okved2 else None

    okopf = source.get("okopf")
    okopf_str: str | None
    if isinstance(okopf, dict):
        okopf_str = " ".join(
            str(v) for v in (okopf.get("code"), okopf.get("name")) if v
        )
    else:
        okopf_str = str(okopf) if okopf else None

    return OrganizationInfo(
        inn=str(source.get("inn") or inn),
        kpp=_str_or_none(source.get("kpp")),
        ogrn=_str_or_none(source.get("ogrn")),
        short_name=_str_or_none(source.get("short_name")),
        full_name=_str_or_none(source.get("full_name")),
        status=_str_or_none(source.get("status")),
        okved2=okved_str,
        okopf=okopf_str,
        address=address,
        org_id=_str_or_none(source.get("id")),
        registration_date=_str_or_none(source.get("registration_date")),
        tax_authority_name=tax_authority_name,
        tax_authority_code=tax_authority_code,
    )


def _aggregate_rows(
    reports_asc: list[dict[str, Any]],
    source_key: str,
    *,
    include_before_previous: bool,
    extract: Any = None,
) -> list[AccountingRow]:
    """Merge rows across all yearly reports keyed by line code.

    parser-api returns one report per filing year with current/previous
    (and before_previous for the balance). Each year's own report is
    authoritative for that year via its ``current`` field. ``previous`` and
    ``before_previous`` only fill in years not covered by any report's
    ``current`` (e.g. years older than the oldest filing on file).
    """
    extract_value = extract if callable(extract) else (lambda v: v)
    aggregated: dict[str, dict[str, Any]] = {}

    def iter_rows(
        raw_report: dict[str, Any],
    ) -> list[tuple[int, str, str, dict[str, Any]]]:
        period = _safe_int(raw_report.get("period"))
        source = raw_report.get(source_key)
        if period is None or not isinstance(source, list):
            return []
        out: list[tuple[int, str, str, dict[str, Any]]] = []
        for raw in source:
            if not isinstance(raw, dict):
                continue
            code = _str_or_none(raw.get("code"))
            name = _str_or_none(raw.get("name"))
            if code and name:
                out.append((period, code, name, raw))
        return out

    # Pass 1: authoritative "current" per report period.
    for raw_report in reports_asc:
        for period, code, name, raw in iter_rows(raw_report):
            entry = aggregated.setdefault(code, {"name": name, "values": {}})
            entry["values"][str(period)] = _as_rubles(
                extract_value(raw.get("current"))
            )

    # Pass 2: fill in previous/before_previous only for years not already set
    # (first writer wins: closest report to the target year).
    for raw_report in reports_asc:
        for period, code, name, raw in iter_rows(raw_report):
            entry = aggregated.setdefault(code, {"name": name, "values": {}})
            values: dict[str, int | None] = entry["values"]
            prev_key = str(period - 1)
            if prev_key not in values:
                values[prev_key] = _as_rubles(
                    extract_value(raw.get("previous"))
                )
            if include_before_previous:
                before_key = str(period - 2)
                if before_key not in values:
                    values[before_key] = _as_rubles(
                        extract_value(raw.get("before_previous"))
                    )

    return [
        AccountingRow(code=code, name=data["name"], values=data["values"])
        for code, data in aggregated.items()
    ]


def _aggregate_capital_change(
    reports_asc: list[dict[str, Any]],
) -> list[AccountingRow]:
    """Merge capital-change rows across all yearly reports.

    parser-api changed schema for ``capital_change``: instead of
    ``current`` / ``previous`` wrappers each row now carries flat fields
    (authorized, unallocated, …) with a ``total`` key.  Each yearly
    report is authoritative for its own period only.
    """
    aggregated: dict[str, dict[str, Any]] = {}

    for raw_report in reports_asc:
        period = _safe_int(raw_report.get("period"))
        source = raw_report.get("capital_change")
        if period is None or not isinstance(source, list):
            continue
        for raw in source:
            if not isinstance(raw, dict):
                continue
            code = _str_or_none(raw.get("code"))
            name = _str_or_none(raw.get("name"))
            if not code or not name:
                continue
            entry = aggregated.setdefault(code, {"name": name, "values": {}})
            entry["values"][str(period)] = _as_rubles(
                _extract_total(raw)
            )

    return [
        AccountingRow(code=code, name=data["name"], values=data["values"])
        for code, data in aggregated.items()
    ]


def _parse_audit(raw: Any) -> AuditReport | None:
    if not isinstance(raw, dict):
        return None
    return AuditReport(
        auditor_name=_str_or_none(raw.get("name") or raw.get("short_name")),
        auditor_inn=_str_or_none(raw.get("inn")),
        auditor_ogrn=_str_or_none(raw.get("ogrn")),
        pdf_url=_str_or_none(raw.get("url") or raw.get("pdf_url")),
    )


def _parse_clarification(raw: Any) -> str | None:
    if isinstance(raw, dict):
        url = raw.get("url")
        return str(url) if url else None
    if isinstance(raw, str):
        return raw or None
    return None


def _extract_total(raw: Any) -> Any:
    if isinstance(raw, dict):
        return raw.get("total")
    return raw


def _as_rubles(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return round(float(value) * _AMOUNT_MULTIPLIER)
    except (TypeError, ValueError):
        return None


def _safe_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _str_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
