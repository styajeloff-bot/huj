"""Persistence boundary for bank statement imports and analytics."""

from __future__ import annotations

from datetime import date
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.models.applications import LeasingApplication
from infrastructure.models.bank_statements import (
    BankAccount,
    BankStatementImport,
    BankTransaction,
    OperationKind,
)
from infrastructure.models.companies import Company
from infrastructure.repository_timing import timed_repository

OPERATION_KINDS: list[dict[str, Any]] = [
    {"id": 1, "name": "Оплата покупателя", "direction": "income"},
    {"id": 2, "name": "Поступление по платежным картам/СБП", "direction": "income"},
    {"id": 3, "name": "Возврат от поставщика", "direction": "income"},
    {"id": 4, "name": "Получение займа", "direction": "income"},
    {"id": 5, "name": "Возврат займа контрагентом", "direction": "income"},
    {"id": 6, "name": "Получение кредита", "direction": "income"},
    {"id": 7, "name": "Взнос в уставный капитал", "direction": "income"},
    {"id": 8, "name": "Перевод с другого счета", "direction": "income"},
    {"id": 9, "name": "Взнос наличными", "direction": "income"},
    {"id": 10, "name": "Возврат налога", "direction": "income"},
    {"id": 11, "name": "Прочие доходы", "direction": "income"},
    {"id": 12, "name": "Оплата поставщику", "direction": "expense"},
    {"id": 13, "name": "Перечисление налога", "direction": "expense"},
    {"id": 14, "name": "Комиссия банка", "direction": "expense"},
    {"id": 15, "name": "Перечисление зарплаты", "direction": "expense"},
    {"id": 16, "name": "Возврат покупателю", "direction": "expense"},
    {"id": 17, "name": "Выдача займа", "direction": "expense"},
    {"id": 18, "name": "Возврат займа", "direction": "expense"},
    {"id": 19, "name": "Возврат кредита", "direction": "expense"},
    {"id": 20, "name": "Перевод на другой счет", "direction": "expense"},
    {"id": 21, "name": "Снятие наличных", "direction": "expense"},
    {"id": 22, "name": "Не определено", "direction": None},
]


def _import_to_dict(row: BankStatementImport) -> dict[str, Any]:
    return {
        "id": row.id,
        "company_id": row.company_id,
        "document_id": row.document_id,
        "file_name": row.file_name,
        "file_sha256": row.file_sha256,
        "encoding": row.encoding,
        "format_version": row.format_version,
        "sender": row.sender,
        "recipient": row.recipient,
        "created_on": row.created_on,
        "period_start": row.period_start,
        "period_end": row.period_end,
        "statement_account": row.statement_account,
        "opening_balance": row.opening_balance,
        "total_income": row.total_income,
        "total_expense": row.total_expense,
        "closing_balance": row.closing_balance,
        "transactions_count": row.transactions_count,
        "status": row.status,
        "error": row.error,
        "raw_header": row.raw_header,
        "raw_account_section": row.raw_account_section,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _account_to_dict(row: BankAccount) -> dict[str, Any]:
    return {
        "id": row.id,
        "company_id": row.company_id,
        "account_number": row.account_number,
        "owner_name": row.owner_name,
        "owner_inn": row.owner_inn,
        "owner_kpp": row.owner_kpp,
        "bank_name": row.bank_name,
        "bik": row.bik,
        "correspondent_account": row.correspondent_account,
        "created_at": row.created_at,
    }


def _transaction_to_dict(row: BankTransaction) -> dict[str, Any]:
    return {
        column.name: getattr(row, column.name)
        for column in BankTransaction.__table__.columns
    }


def _application_access_to_dict(row: LeasingApplication) -> dict[str, Any]:
    return {
        "id": row.id,
        "company_id": row.company_id,
        "dealer_company_id": row.dealer_company_id,
        "selected_leasing_companies": list(row.selected_leasing_companies)
        if row.selected_leasing_companies is not None
        else [],
    }


@timed_repository
async def get_operation_kind_by_name(
    session: AsyncSession, name: str
) -> dict[str, Any] | None:
    row = (
        await session.execute(sa.select(OperationKind).where(OperationKind.name == name))
    ).scalar_one_or_none()
    if row is None:
        return None
    return {"id": row.id, "name": row.name, "direction": row.direction}


async def _operation_kind_ids(session: AsyncSession) -> dict[str, int]:
    rows = (await session.execute(sa.select(OperationKind))).scalars().all()
    if not rows:
        session.add_all([OperationKind(**item) for item in OPERATION_KINDS])
        await session.flush()
        rows = (await session.execute(sa.select(OperationKind))).scalars().all()
    return {row.name: row.id for row in rows}


@timed_repository
async def create_import(session: AsyncSession, **values: Any) -> dict[str, Any]:
    row = BankStatementImport(**values)
    session.add(row)
    await session.flush()
    await session.refresh(row)
    return _import_to_dict(row)


@timed_repository
async def mark_import_failed(
    session: AsyncSession, import_id: UUID, error: str
) -> dict[str, Any] | None:
    row = await session.get(BankStatementImport, import_id)
    if row is None:
        return None
    row.status = "failed"
    row.error = error
    await session.flush()
    await session.refresh(row)
    return _import_to_dict(row)


@timed_repository
async def get_import_by_checksum(
    session: AsyncSession, company_id: UUID, file_sha256: str
) -> dict[str, Any] | None:
    row = (
        await session.execute(
            sa.select(BankStatementImport).where(
                BankStatementImport.company_id == company_id,
                BankStatementImport.file_sha256 == file_sha256,
            )
        )
    ).scalar_one_or_none()
    return _import_to_dict(row) if row is not None else None


@timed_repository
async def get_application_access_projection(
    session: AsyncSession, application_id: UUID
) -> dict[str, Any] | None:
    row = await session.get(LeasingApplication, application_id)
    return _application_access_to_dict(row) if row is not None else None


@timed_repository
async def company_has_selected_lc_application(
    session: AsyncSession,
    *,
    company_id: UUID,
    leasing_company_id: UUID,
) -> bool:
    stmt = (
        sa.select(LeasingApplication.id)
        .where(
            LeasingApplication.company_id == company_id,
            LeasingApplication.selected_leasing_companies.contains([leasing_company_id]),
        )
        .limit(1)
    )
    return (await session.execute(stmt)).first() is not None


@timed_repository
async def upsert_client_accounts(
    session: AsyncSession, company_id: UUID, accounts: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for account in accounts:
        values = {"company_id": company_id, **account}
        stmt = (
            pg_insert(BankAccount)
            .values(**values)
            .on_conflict_do_nothing(
                index_elements=[BankAccount.company_id, BankAccount.account_number]
            )
        )
        await session.execute(stmt)
        stored = (
            await session.execute(
                sa.select(BankAccount).where(
                    BankAccount.company_id == company_id,
                    BankAccount.account_number == account["account_number"],
                )
            )
        ).scalar_one()
        out.append(_account_to_dict(stored))
    await session.flush()
    return out


@timed_repository
async def insert_transactions(
    session: AsyncSession, transactions: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    kind_ids = await _operation_kind_ids(session)
    out: list[BankTransaction] = []
    for item in transactions:
        values = dict(item)
        operation_kind = str(values.get("operation_kind") or "")
        values["operation_kind_id"] = kind_ids.get(operation_kind)
        row = BankTransaction(**values)
        session.add(row)
        out.append(row)
    await session.flush()
    return [_transaction_to_dict(row) for row in out]


@timed_repository
async def list_accounts_by_company(
    session: AsyncSession, company_id: UUID
) -> list[dict[str, Any]]:
    rows = (
        await session.execute(
            sa.select(BankAccount)
            .where(BankAccount.company_id == company_id)
            .order_by(BankAccount.account_number)
        )
    ).scalars().all()
    return [_account_to_dict(row) for row in rows]


@timed_repository
async def list_transactions_by_company(
    session: AsyncSession,
    company_id: UUID,
    *,
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[dict[str, Any]]:
    stmt = sa.select(BankTransaction).where(BankTransaction.company_id == company_id)
    if start_date is not None:
        stmt = stmt.where(BankTransaction.document_date >= start_date)
    if end_date is not None:
        stmt = stmt.where(BankTransaction.document_date <= end_date)
    rows = (await session.execute(stmt.order_by(BankTransaction.document_date))).scalars().all()
    return [_transaction_to_dict(row) for row in rows]


@timed_repository
async def get_company_bank_analytics_source(
    session: AsyncSession, company_id: UUID
) -> dict[str, Any] | None:
    company = await session.get(Company, company_id)
    if company is None:
        return None
    imports = (
        await session.execute(
            sa.select(BankStatementImport)
            .where(BankStatementImport.company_id == company_id)
            .order_by(BankStatementImport.period_end)
        )
    ).scalars().all()
    return {
        "company": {"id": company.id, "name": company.name, "inn": company.inn},
        "accounts": await list_accounts_by_company(session, company_id),
        "transactions": await list_transactions_by_company(session, company_id),
        "imports": [_import_to_dict(row) for row in imports],
    }


@timed_repository
async def get_company(session: AsyncSession, company_id: UUID) -> dict[str, Any] | None:
    company = await session.get(Company, company_id)
    if company is None:
        return None
    return {"id": company.id, "name": company.name, "inn": company.inn}
