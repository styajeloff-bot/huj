"""Pydantic schemas for bank statement upload and analytics endpoints."""

from __future__ import annotations

from datetime import date
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class BankStatementUploadItemResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    file_name: str
    import_id: UUID
    document_id: UUID | None
    status: str
    transactions_count: int
    recognized_transactions_count: int
    accounts_count: int
    period_start: date | None
    period_end: date | None


class BankStatementUploadResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[BankStatementUploadItemResponse]
    total_transactions_count: int
    total_recognized_transactions_count: int


class BankStatementCompanyResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    name: str
    inn: str | None


class BankStatementAccountResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_number: str
    bank_name: str


class BankStatementPeriodResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start: date
    end: date


class BankStatementKpiResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    income: float
    expense: float
    turnover: float
    average_monthly_turnover: float
    external_revenue: float
    opening_balance: float
    closing_balance: float
    balance_change: float


class BankStatementCashflowPointResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    month: str
    income: float
    expense: float
    closing_balance: float


class BankStatementExpenseSliceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation_kind: str
    amount: float
    share: float


class BankStatementCounterpartyResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str
    inn: str | None
    amount: float
    is_self_transfer: bool


class BankStatementAnalyticsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    company: BankStatementCompanyResponse
    accounts: list[BankStatementAccountResponse]
    period: BankStatementPeriodResponse | None
    kpi: BankStatementKpiResponse
    cashflow: list[BankStatementCashflowPointResponse]
    expense_structure: list[BankStatementExpenseSliceResponse]
    top_clients: list[BankStatementCounterpartyResponse]
    top_suppliers: list[BankStatementCounterpartyResponse]
    empty: bool
