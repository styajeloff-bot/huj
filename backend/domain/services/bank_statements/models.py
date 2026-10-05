"""Dataclasses produced by the 1CClientBankExchange parser."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any


@dataclass(frozen=True)
class ParsedBankAccountSection:
    account_number: str | None
    period_start: date | None
    period_end: date | None
    opening_balance: Decimal | None
    total_income: Decimal | None
    total_expense: Decimal | None
    closing_balance: Decimal | None
    raw_section: dict[str, Any]


@dataclass(frozen=True)
class ParsedBankOperation:
    document_section: str
    document_number: str | None
    document_date: date | None
    amount: Decimal
    payer_account: str | None
    payer_correspondent: str | None
    payer_write_off_date: date | None
    payer_inn: str | None
    payer_name: str | None
    payer_bank_name: str | None
    payer_bik: str | None
    payer_kpp: str | None
    recipient_account: str | None
    recipient_receipt_date: date | None
    recipient_inn: str | None
    recipient_name: str | None
    recipient_bank_name: str | None
    recipient_bik: str | None
    recipient_kpp: str | None
    recipient_correspondent: str | None
    payment_type: str | None
    payment_code: str | None
    priority: int | None
    payment_purpose: str | None
    raw_operation: dict[str, Any]


@dataclass(frozen=True)
class ParsedBankStatement:
    encoding: str
    format_version: str | None
    sender: str | None
    recipient: str | None
    created_on: date | None
    period_start: date | None
    period_end: date | None
    statement_account: str | None
    accounts: list[ParsedBankAccountSection]
    operations: list[ParsedBankOperation]
    raw_header: dict[str, Any]
