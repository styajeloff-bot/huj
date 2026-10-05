"""Domain value objects for accounting/financial reports.

Provider-agnostic normalized shapes returned by `AccountingProvider`
implementations. The HTTP layer serializes them directly — no
provider-specific fields leak out.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

RatioBand = Literal["good", "warn", "bad", "unknown"]


@dataclass(frozen=True)
class AccountingRow:
    """One line of a financial form (balance, P&L, cash flow).

    `values` maps year (as a 4-digit string) to the reported amount in
    roubles (тыс. руб. → multiply by 1000 in the provider adapter).
    `None` means the period exists but the value is not reported.
    """

    code: str
    name: str
    values: dict[str, int | None]


@dataclass(frozen=True)
class AuditReport:
    auditor_name: str | None
    auditor_inn: str | None
    auditor_ogrn: str | None
    pdf_url: str | None


@dataclass(frozen=True)
class OrganizationInfo:
    inn: str
    kpp: str | None
    ogrn: str | None
    short_name: str | None
    full_name: str | None
    status: str | None
    okved2: str | None
    okopf: str | None
    address: str | None
    # ФНС `orgId` (from bo.nalog.gov.ru) — needed to build PDF / signed-archive URLs.
    org_id: str | None = None
    registration_date: str | None = None
    tax_authority_name: str | None = None
    tax_authority_code: str | None = None


@dataclass(frozen=True)
class AccountingYearFile:
    """Downloadable files associated with one yearly BFO submission.

    parser-api returns a `reports[]` array — one item per submission. Each
    item carries links back to bo.nalog.gov.ru for the unsigned PDF, the
    audit PDF (if any), and the clarification PDF (if any). `detail_id` is
    the ФНС submission id and is the anchor for the signed-archive proxy.
    """

    year: int
    detail_id: str | None
    pdf_url: str | None
    audit_pdf_url: str | None
    clarification_pdf_url: str | None


@dataclass(frozen=True)
class AccountingReport:
    """Aggregate: everything we have for a single company from an ФНС-like source."""

    inn: str
    period_years: list[int]
    organization: OrganizationInfo
    balance_sheet: list[AccountingRow]
    financial_result: list[AccountingRow]
    cash_flow: list[AccountingRow]
    capital_change: list[AccountingRow]
    audit_report: AuditReport | None
    clarification_url: str | None
    year_files: list[AccountingYearFile] = field(default_factory=list)


@dataclass(frozen=True)
class FinancialRatio:
    """One computed financial ratio with traffic-light band and human hint."""

    key: str
    name: str
    value: float | None
    band: RatioBand
    hint: str
    formula: str
