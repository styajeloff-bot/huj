"""HTTP schemas for accounting reports (OpenAPI docs only).

FastAPI does not validate JSONResponse payloads against `response_model`,
but these schemas drive Swagger documentation.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class AccountingRowResponse(BaseModel):
    code: str
    name: str
    values: dict[str, int | None] = Field(default_factory=dict)


class AuditReportResponse(BaseModel):
    auditor_name: str | None = None
    auditor_inn: str | None = None
    auditor_ogrn: str | None = None
    pdf_url: str | None = None


class OrganizationInfoResponse(BaseModel):
    inn: str
    kpp: str | None = None
    ogrn: str | None = None
    short_name: str | None = None
    full_name: str | None = None
    status: str | None = None
    okved2: str | None = None
    okopf: str | None = None
    address: str | None = None
    org_id: str | None = None
    registration_date: str | None = None
    tax_authority_name: str | None = None
    tax_authority_code: str | None = None


class AccountingYearFileResponse(BaseModel):
    year: int
    detail_id: str | None = None
    pdf_url: str | None = None
    audit_pdf_url: str | None = None
    clarification_pdf_url: str | None = None


class FinancialRatioResponse(BaseModel):
    key: str
    name: str
    value: float | None = None
    band: str
    hint: str
    formula: str


class AccountingReportResponse(BaseModel):
    inn: str
    company_id: str | None = None
    provider_name: str
    period_years: list[int] = Field(default_factory=list)
    organization: OrganizationInfoResponse | None = None
    balance_sheet: list[AccountingRowResponse] = Field(default_factory=list)
    financial_result: list[AccountingRowResponse] = Field(default_factory=list)
    cash_flow: list[AccountingRowResponse] = Field(default_factory=list)
    capital_change: list[AccountingRowResponse] = Field(default_factory=list)
    audit_report: AuditReportResponse | None = None
    clarification_url: str | None = None
    year_files: list[AccountingYearFileResponse] = Field(default_factory=list)
    computed_ratios: list[FinancialRatioResponse] = Field(default_factory=list)
    fetch_status: str
    last_fetch_at: str | None = None
    cached: bool = False
    stale: bool = False

    model_config = {"extra": "allow"}


class AccountingErrorResponse(BaseModel):
    detail: str | dict[str, Any]


class AccountingHistoryUpload(BaseModel):
    date: str | None = None
    source_type: str
    row_count: int


class AccountingHistoryYear(BaseModel):
    year: int
    uploads: list[AccountingHistoryUpload] = Field(default_factory=list)


class AccountingHistoryResponse(BaseModel):
    inn: str
    years: list[AccountingHistoryYear] = Field(default_factory=list)
