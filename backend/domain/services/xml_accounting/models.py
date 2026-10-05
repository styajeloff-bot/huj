"""Domain models for parsed accounting report data."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass(frozen=True)
class ReportTypeInfo:
    """Detected report type from XML header."""

    knd: str
    okud: str
    report_type: Literal["balance_sheet", "financial_result", "capital_changes", "cash_flow", "nds_declaration"]
    name: str


@dataclass(frozen=True)
class ExtractedMetadata:
    """Company and period metadata extracted from XML."""

    inn: str
    kpp: str | None
    company_name: str | None
    report_year: int
    period_code: int  # 31=1кв, 32=полугодие, 33=9мес, 34=год
    period_name: str
    okei_code: str | None
    okud: str
    source_type: Literal["api_fns", "xml_file"] = "xml_file"


@dataclass(frozen=True)
class ParsedRow:
    """One normalized row ready for database upsert."""

    line_code: str
    line_name: str
    amount: float | None = None
    amount_prev: float | None = None
    amount_before_prev: float | None = None
    component_code: str | None = None
    component_name: str | None = None
    tax_amount: float | None = None
    total_tax_payable: float | None = None
    total_deductions: float | None = None
    total_recovered: float | None = None
    # Raw XML snippet for debugging / audit
    xml_raw: dict | None = None


@dataclass(frozen=True)
class ParsedReport:
    """Complete parse result: metadata + all rows."""

    metadata: ExtractedMetadata
    rows: list[ParsedRow] = field(default_factory=list)
