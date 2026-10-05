from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.models.companies import Company
from infrastructure.repositories import bank_statement_repository as repo

pytestmark = pytest.mark.asyncio


async def test_operation_kind_seed_contract_has_22_values() -> None:
    names = [item["name"] for item in repo.OPERATION_KINDS]

    assert len(names) == 22
    assert "Не определено" in names
    assert "Оплата покупателя" in names
    assert "Оплата поставщику" in names


async def test_upsert_client_accounts_is_idempotent(db_session: AsyncSession) -> None:
    company = Company(name="Test Company", inn="501906237893", company_type="other")
    db_session.add(company)
    await db_session.flush()
    company_id = company.id
    account = {
        "account_number": "40802810000000360978",
        "owner_name": "ИП Леонов Илья Константинович",
        "owner_inn": "501906237893",
        "owner_kpp": None,
        "bank_name": 'ООО "ОЗОН БАНК"',
        "bik": "044525068",
        "correspondent_account": None,
    }

    first = await repo.upsert_client_accounts(db_session, company_id, [account])
    second = await repo.upsert_client_accounts(db_session, company_id, [account])

    assert len(first) == 1
    assert len(second) == 1
    stored = await repo.list_accounts_by_company(db_session, company_id)
    assert len(stored) == 1
    assert stored[0]["account_number"] == account["account_number"]


async def test_insert_transactions_stores_raw_operation_and_operation_kind_id(
    db_session: AsyncSession,
) -> None:
    company = Company(name="Test Company", inn="501906237893", company_type="other")
    db_session.add(company)
    await db_session.flush()
    company_id = company.id
    import_row = await repo.create_import(
        db_session,
        company_id=company_id,
        document_id=None,
        file_name="statement.txt",
        file_sha256="a" * 64,
        encoding="cp1251",
        format_version="1.03",
        sender="bank",
        recipient="1c",
        created_on=None,
        period_start=None,
        period_end=None,
        statement_account="40802810000000360978",
        opening_balance=Decimal("0.00"),
        total_income=Decimal("10.00"),
        total_expense=Decimal("0.00"),
        closing_balance=Decimal("10.00"),
        transactions_count=1,
        raw_header={"ВерсияФормата": "1.03"},
        raw_account_section={"РасчСчет": "40802810000000360978"},
    )

    rows = await repo.insert_transactions(
        db_session,
        [
            {
                "import_id": import_row["id"],
                "company_id": company_id,
                "operation_kind": "Оплата покупателя",
                "direction": "income",
                "document_section": "Платежное поручение",
                "document_number": "1",
                "document_date": None,
                "execution_date": None,
                "amount": Decimal("10.00"),
                "payer_account": "40702810300000051346",
                "payer_correspondent": "30101810000000000225",
                "recipient_account": "40802810000000360978",
                "raw_operation": {"НазначениеПлатежа": "Оплата"},
            }
        ],
    )

    assert rows[0]["operation_kind_id"] is not None
    assert rows[0]["payer_correspondent"] == "30101810000000000225"
    assert rows[0]["raw_operation"] == {"НазначениеПлатежа": "Оплата"}
