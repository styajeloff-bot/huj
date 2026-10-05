from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from application.queries.bank_statement_analytics import (
    GetBankStatementAnalyticsQuery,
    handle_get_bank_statement_analytics,
)
from infrastructure.models.companies import Company
from infrastructure.repositories import bank_statement_repository as repo
from infrastructure.repositories import company_repository

pytestmark = pytest.mark.asyncio


async def _company(db_session: AsyncSession) -> Company:
    row = Company(
        name="ИП Леонов Илья Константинович",
        inn="501906237893",
        company_type="other",
    )
    db_session.add(row)
    await db_session.flush()
    return row


async def test_analytics_excludes_self_transfers_from_kpi(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    company = await _company(db_session)
    company_id = company.id
    import_row = await repo.create_import(
        db_session,
        company_id=company_id,
        document_id=None,
        file_name="statement.txt",
        file_sha256="b" * 64,
        encoding="cp1251",
        format_version="1.03",
        sender=None,
        recipient=None,
        created_on=None,
        period_start=date(2025, 6, 1),
        period_end=date(2025, 7, 31),
        statement_account="40802810000000360978",
        opening_balance=Decimal("100.00"),
        total_income=Decimal("1300.00"),
        total_expense=Decimal("700.00"),
        closing_balance=Decimal("700.00"),
        transactions_count=4,
        raw_header={},
        raw_account_section={},
    )
    await repo.insert_transactions(
        db_session,
        [
            {
                "import_id": import_row["id"],
                "company_id": company_id,
                "operation_kind": "Оплата покупателя",
                "direction": "income",
                "document_date": date(2025, 6, 15),
                "amount": Decimal("1000.00"),
                "counterparty_name": "Client",
                "counterparty_inn": "7704217370",
                "is_self_transfer": False,
                "raw_operation": {},
            },
            {
                "import_id": import_row["id"],
                "company_id": company_id,
                "operation_kind": "Оплата поставщику",
                "direction": "expense",
                "document_date": date(2025, 6, 16),
                "amount": Decimal("500.00"),
                "counterparty_name": "Supplier",
                "counterparty_inn": "9703077050",
                "is_self_transfer": False,
                "raw_operation": {},
            },
            {
                "import_id": import_row["id"],
                "company_id": company_id,
                "operation_kind": "Перевод с другого счета",
                "direction": "income",
                "document_date": date(2025, 7, 1),
                "amount": Decimal("300.00"),
                "counterparty_name": "Own",
                "counterparty_inn": "501906237893",
                "is_self_transfer": True,
                "raw_operation": {},
            },
        ],
    )
    monkeypatch.setattr(
        "application.queries.bank_statement_analytics._now",
        lambda: datetime(2026, 6, 22, tzinfo=UTC),
    )

    result = await handle_get_bank_statement_analytics(
        GetBankStatementAnalyticsQuery(company_id=company_id),
        db_session,
        {"id": uuid4(), "role": "client", "company_id": str(company_id)},
    )

    assert result["empty"] is False
    assert result["kpi"]["income"] == 1000.0
    assert result["kpi"]["expense"] == 500.0
    assert result["kpi"]["turnover"] == 1500.0
    assert result["kpi"]["external_revenue"] == 1000.0
    assert result["top_suppliers"][0]["display_name"] == "Supplier"


async def test_analytics_returns_empty_shape_without_transactions(
    db_session: AsyncSession,
) -> None:
    company = await _company(db_session)

    result = await handle_get_bank_statement_analytics(
        GetBankStatementAnalyticsQuery(company_id=company.id),
        db_session,
        {"id": uuid4(), "role": "client", "company_id": str(company.id)},
    )

    assert result["empty"] is True
    assert result["period"] is None
    assert result["cashflow"] == []


async def test_client_can_read_analytics_for_linked_non_primary_company(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    company = await _company(db_session)
    user_id = uuid4()

    async def is_linked(
        session: AsyncSession,
        candidate_user_id: UUID,
        candidate_company_id: UUID,
    ) -> bool:
        assert session is db_session
        return candidate_user_id == user_id and candidate_company_id == company.id

    monkeypatch.setattr(company_repository, "is_user_linked_to_company", is_linked)

    result = await handle_get_bank_statement_analytics(
        GetBankStatementAnalyticsQuery(company_id=company.id),
        db_session,
        {"id": user_id, "role": "client", "company_id": None},
    )

    assert result["company"]["id"] == company.id
    assert result["empty"] is True


async def test_analytics_uses_period_bounded_balances_per_account(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    company = await _company(db_session)
    company_id = company.id
    older_import = await repo.create_import(
        db_session,
        company_id=company_id,
        document_id=None,
        file_name="old.txt",
        file_sha256="c" * 64,
        encoding="cp1251",
        format_version="1.03",
        sender=None,
        recipient=None,
        created_on=None,
        period_start=date(2024, 1, 1),
        period_end=date(2024, 1, 31),
        statement_account="40802810000000000001",
        opening_balance=Decimal("10000.00"),
        total_income=Decimal("0.00"),
        total_expense=Decimal("0.00"),
        closing_balance=Decimal("9000.00"),
        transactions_count=0,
        raw_header={},
        raw_account_section={},
    )
    first_account_import = await repo.create_import(
        db_session,
        company_id=company_id,
        document_id=None,
        file_name="a.txt",
        file_sha256="d" * 64,
        encoding="cp1251",
        format_version="1.03",
        sender=None,
        recipient=None,
        created_on=None,
        period_start=date(2025, 1, 1),
        period_end=date(2025, 1, 31),
        statement_account="40802810000000000001",
        opening_balance=Decimal("100.00"),
        total_income=Decimal("50.00"),
        total_expense=Decimal("0.00"),
        closing_balance=Decimal("150.00"),
        transactions_count=1,
        raw_header={},
        raw_account_section={},
    )
    second_account_import = await repo.create_import(
        db_session,
        company_id=company_id,
        document_id=None,
        file_name="b.txt",
        file_sha256="e" * 64,
        encoding="cp1251",
        format_version="1.03",
        sender=None,
        recipient=None,
        created_on=None,
        period_start=date(2025, 2, 1),
        period_end=date(2025, 2, 28),
        statement_account="40802810000000000002",
        opening_balance=Decimal("200.00"),
        total_income=Decimal("50.00"),
        total_expense=Decimal("0.00"),
        closing_balance=Decimal("250.00"),
        transactions_count=1,
        raw_header={},
        raw_account_section={},
    )
    await repo.insert_transactions(
        db_session,
        [
            {
                "import_id": older_import["id"],
                "company_id": company_id,
                "operation_kind": "Оплата покупателя",
                "direction": "income",
                "document_date": date(2024, 1, 10),
                "amount": Decimal("1.00"),
                "is_self_transfer": False,
                "raw_operation": {},
            },
            {
                "import_id": first_account_import["id"],
                "company_id": company_id,
                "operation_kind": "Оплата покупателя",
                "direction": "income",
                "document_date": date(2025, 1, 10),
                "amount": Decimal("50.00"),
                "is_self_transfer": False,
                "raw_operation": {},
            },
            {
                "import_id": second_account_import["id"],
                "company_id": company_id,
                "operation_kind": "Оплата покупателя",
                "direction": "income",
                "document_date": date(2025, 2, 10),
                "amount": Decimal("50.00"),
                "is_self_transfer": False,
                "raw_operation": {},
            },
        ],
    )
    monkeypatch.setattr(
        "application.queries.bank_statement_analytics._now",
        lambda: datetime(2026, 6, 22, tzinfo=UTC),
    )

    result = await handle_get_bank_statement_analytics(
        GetBankStatementAnalyticsQuery(company_id=company_id),
        db_session,
        {"id": uuid4(), "role": "client", "company_id": str(company_id)},
    )

    assert result["kpi"]["opening_balance"] == 300.0
    assert result["kpi"]["closing_balance"] == 400.0
    assert result["kpi"]["balance_change"] == 100.0
