"""Update one application from actually parsed bank-statement counterparties."""
from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from domain.bank_statement_counterparties import questionnaire_counterparties
from infrastructure.repositories import application_repository as applications
from infrastructure.repositories import bank_statement_repository as statements


async def refresh_bank_counterparties(session: AsyncSession, application_id: UUID) -> None:
    application = await applications.get_by_id(session, application_id, for_update=True)
    if application is None:
        return
    transactions = await statements.list_transactions_by_company(session, application["company_id"])
    counterparties = questionnaire_counterparties(transactions, today=datetime.now(UTC).date())
    if counterparties:
        await applications.upsert_questionnaire(
            session, application_id=application_id,
            payload={"main_counterparties": counterparties}, source="bank_statement",
        )
