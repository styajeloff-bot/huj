"""Use-case for uploading and persisting bank statement text files."""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.errors import ServiceError
from application.permissions import ensure_application_owned_by
from application.services.questionnaire_bank import refresh_bank_counterparties
from domain.services.bank_statements.models import (
    ParsedBankAccountSection,
    ParsedBankOperation,
    ParsedBankStatement,
)
from domain.services.bank_statements.parser import parse_bank_statement
from domain.services.object_storage import ObjectStorage
from infrastructure.repositories import bank_statement_repository as repo
from infrastructure.repositories import documents_repository as docs_repo

_SELF_TRANSFER_KINDS = {"Перевод на другой счет", "Перевод с другого счета"}
_UPLOAD_ALLOWED_ROLES = {"client", "dealer", "carcraft_employee"}

try:
    from carcraft_bor import recognize_bank_operation
except ModuleNotFoundError:
    def recognize_bank_operation(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        raise ServiceError("Модуль распознавания банковских операций недоступен", 503)


@dataclass(frozen=True)
class BankStatementUploadFile:
    filename: str
    data: bytes


async def upload_bank_statements(
    session: AsyncSession,
    *,
    files: list[BankStatementUploadFile],
    storage: ObjectStorage,
    actor_user_id: UUID,
    actor_role: str,
    actor_company_id: UUID | None,
    application_id: UUID | None,
) -> dict[str, Any]:
    if application_id is None:
        raise ServiceError("Не удалось определить заявку для загрузки выписки", 400)
    if actor_role not in _UPLOAD_ALLOWED_ROLES:
        raise ServiceError("Недостаточно прав доступа", 403)

    application = await repo.get_application_access_projection(session, application_id)
    if application is None:
        raise ServiceError("Заявка не найдена", 404)
    await ensure_application_owned_by(
        session,
        application=application,
        user_id=actor_user_id,
        actor_role=actor_role,
        actor_company_id=actor_company_id,
    )

    company_id = application["company_id"]
    company = await repo.get_company(session, company_id)
    if company is None or not company.get("inn"):
        raise ServiceError("Не удалось определить компанию заявки", 400)
    company_inn = _digits(str(company["inn"]))
    if not company_inn:
        raise ServiceError("Не удалось определить ИНН компании заявки", 400)

    items = [
        await _upload_one(
            session,
            file=file,
            storage=storage,
            company_id=company_id,
            company_inn=company_inn,
            application_id=application_id,
        )
        for file in files
    ]

    await refresh_bank_counterparties(session, application_id)

    return {
        "items": items,
        "total_transactions_count": sum(item["transactions_count"] for item in items),
        "total_recognized_transactions_count": sum(
            item["recognized_transactions_count"] for item in items
        ),
    }


async def _upload_one(
    session: AsyncSession,
    *,
    file: BankStatementUploadFile,
    storage: ObjectStorage,
    company_id: UUID,
    company_inn: str,
    application_id: UUID,
) -> dict[str, Any]:
    statement = parse_bank_statement(file.data)
    _validate_statement_ownership(statement, company_inn)

    checksum = hashlib.sha256(file.data).hexdigest()
    existing = await repo.get_import_by_checksum(session, company_id, checksum)
    if existing is not None:
        return _summary(existing, accounts_count=0, recognized_transactions_count=existing["transactions_count"])

    import_id = uuid.uuid4()
    s3_key = f"bank-statements/{company_id}/{import_id}/{file.filename}"
    stored_path = await storage.put(
        s3_key, file.data, f"text/plain; charset={statement.encoding}"
    )
    document_id = await docs_repo.create_document(
        session,
        company_id=company_id,
        document_type="bank_statement_txt",
        file_name=file.filename,
        s3_key=s3_key,
        file_path=stored_path,
        file_size=len(file.data),
        related_application_id=application_id,
        status="uploaded",
        review_status="approved",
    )
    await docs_repo.link_to_application(
        session, document_id=document_id, application_id=application_id
    )

    import_row = await repo.create_import(
        session,
        id=import_id,
        company_id=company_id,
        document_id=document_id,
        file_name=file.filename,
        file_sha256=checksum,
        encoding=statement.encoding,
        format_version=statement.format_version,
        sender=statement.sender,
        recipient=statement.recipient,
        created_on=statement.created_on,
        period_start=statement.period_start,
        period_end=statement.period_end,
        statement_account=statement.statement_account,
        opening_balance=statement.accounts[0].opening_balance if statement.accounts else None,
        total_income=statement.accounts[0].total_income if statement.accounts else None,
        total_expense=statement.accounts[0].total_expense if statement.accounts else None,
        closing_balance=statement.accounts[0].closing_balance if statement.accounts else None,
        transactions_count=len(statement.operations),
        raw_header=statement.raw_header,
        raw_account_section=statement.accounts[0].raw_section if statement.accounts else {},
    )

    accounts = _own_accounts(statement.accounts, statement.operations, company_inn)
    stored_accounts = await repo.upsert_client_accounts(session, company_id, accounts)
    own_accounts = [account["account_number"] for account in stored_accounts]
    transactions = [
        _transaction(import_id, company_id, operation, company_inn, own_accounts)
        for operation in statement.operations
    ]
    inserted = await repo.insert_transactions(session, transactions)

    return _summary(
        import_row,
        accounts_count=len(stored_accounts),
        recognized_transactions_count=sum(
            1 for row in inserted if row["operation_kind"] != "Не определено"
        ),
    )


def _summary(
    import_row: dict[str, Any],
    *,
    accounts_count: int,
    recognized_transactions_count: int,
) -> dict[str, Any]:
    return {
        "file_name": import_row["file_name"],
        "import_id": import_row["id"],
        "document_id": import_row["document_id"],
        "status": import_row["status"],
        "transactions_count": import_row["transactions_count"],
        "recognized_transactions_count": recognized_transactions_count,
        "accounts_count": accounts_count,
        "period_start": import_row["period_start"],
        "period_end": import_row["period_end"],
    }


def _digits(value: str | None) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def _validate_statement_ownership(
    statement: ParsedBankStatement,
    company_inn: str,
) -> None:
    statement_account = _digits(statement.statement_account)
    if not statement_account:
        raise ServiceError(
            "Выписка не принадлежит выбранной компании. Проверьте файл или выберите правильную компанию.",
            422,
        )

    owner_inns = _statement_account_owner_inns(statement, statement_account)
    if not owner_inns:
        raise ServiceError(
            "Выписка не принадлежит выбранной компании. Проверьте файл или выберите правильную компанию.",
            422,
        )
    wrong_owner = next((inn for inn in owner_inns if inn != company_inn), None)
    if wrong_owner is not None:
        raise ServiceError(
            f"Выписка по счету принадлежит организации с ИНН {wrong_owner}, а не выбранной компании",
            422,
        )

    for operation in statement.operations:
        payer_inn = _digits(operation.payer_inn)
        recipient_inn = _digits(operation.recipient_inn)
        if company_inn not in (payer_inn, recipient_inn):
            raise ServiceError(
                "Выписка не принадлежит выбранной компании. Проверьте файл или выберите правильную компанию.",
                422,
            )


def _statement_account_owner_inns(
    statement: ParsedBankStatement,
    statement_account: str,
) -> list[str]:
    owners: list[str] = []
    seen: set[str] = set()
    for operation in statement.operations:
        candidates = (
            (_digits(operation.payer_account), _digits(operation.payer_inn)),
            (_digits(operation.recipient_account), _digits(operation.recipient_inn)),
        )
        for account, inn in candidates:
            if account == statement_account and inn and inn not in seen:
                seen.add(inn)
                owners.append(inn)
    return owners


def _own_accounts(
    account_sections: list[ParsedBankAccountSection],
    operations: list[ParsedBankOperation],
    company_inn: str,
) -> list[dict[str, Any]]:
    by_number: dict[str, dict[str, Any]] = {}
    section_accounts = {section.account_number for section in account_sections}
    for operation in operations:
        if operation.payer_inn == company_inn and operation.payer_account:
            by_number[operation.payer_account] = {
                "account_number": operation.payer_account,
                "owner_name": operation.payer_name or "",
                "owner_inn": operation.payer_inn,
                "owner_kpp": operation.payer_kpp,
                "bank_name": operation.payer_bank_name or "",
                "bik": operation.payer_bik or "",
                "correspondent_account": operation.payer_correspondent,
            }
        if operation.recipient_inn == company_inn and operation.recipient_account:
            by_number[operation.recipient_account] = {
                "account_number": operation.recipient_account,
                "owner_name": operation.recipient_name or "",
                "owner_inn": operation.recipient_inn,
                "owner_kpp": operation.recipient_kpp,
                "bank_name": operation.recipient_bank_name or "",
                "bik": operation.recipient_bik or "",
                "correspondent_account": operation.recipient_correspondent,
            }
    for section in account_sections:
        if section.account_number in section_accounts and section.account_number in by_number:
            continue
    return list(by_number.values())


def _transaction(
    import_id: UUID,
    company_id: UUID,
    operation: ParsedBankOperation,
    company_inn: str,
    own_accounts: list[str],
) -> dict[str, Any]:
    recognized = recognize_bank_operation(
        operation.raw_operation, own_accounts=own_accounts
    )
    operation_kind = str(recognized.get("operation_kind") or "Не определено")
    direction = _direction(str(recognized.get("direction") or ""))
    payer_account = operation.payer_account
    recipient_account = operation.recipient_account
    self_transfer = (
        operation.payer_inn == company_inn
        and operation.recipient_inn == company_inn
    ) or (
        operation_kind in _SELF_TRANSFER_KINDS
        and bool(payer_account in own_accounts and recipient_account in own_accounts)
    )
    return {
        "import_id": import_id,
        "company_id": company_id,
        "operation_kind": operation_kind,
        "direction": direction,
        "document_section": operation.document_section,
        "document_number": operation.document_number,
        "document_date": operation.document_date,
        "execution_date": operation.recipient_receipt_date or operation.payer_write_off_date or operation.document_date,
        "amount": Decimal(str(recognized.get("amount") or operation.amount)),
        "payer_account": payer_account,
        "payer_correspondent": operation.payer_correspondent,
        "payer_write_off_date": operation.payer_write_off_date,
        "payer_inn": operation.payer_inn,
        "payer_name": operation.payer_name,
        "payer_bank_name": operation.payer_bank_name,
        "payer_bik": operation.payer_bik,
        "payer_kpp": operation.payer_kpp,
        "recipient_account": recipient_account,
        "recipient_receipt_date": operation.recipient_receipt_date,
        "recipient_inn": operation.recipient_inn,
        "recipient_name": operation.recipient_name,
        "recipient_bank_name": operation.recipient_bank_name,
        "recipient_bik": operation.recipient_bik,
        "recipient_kpp": operation.recipient_kpp,
        "recipient_correspondent": operation.recipient_correspondent,
        "kbk": operation.raw_operation.get("ПоказательКБК") or operation.raw_operation.get("КБК"),
        "okato": operation.raw_operation.get("ОКАТО") or operation.raw_operation.get("ОКТМО"),
        "tax_reason": operation.raw_operation.get("ПоказательОснования"),
        "tax_period": operation.raw_operation.get("ПоказательПериода"),
        "tax_document_number": operation.raw_operation.get("ПоказательНомера"),
        "tax_document_date": operation.raw_operation.get("ПоказательДаты"),
        "tax_payer_status": operation.raw_operation.get("СтатусСоставителя"),
        "payment_type": operation.payment_type,
        "payment_code": operation.payment_code,
        "priority": operation.priority,
        "payment_purpose": operation.payment_purpose,
        "is_self_transfer": self_transfer,
        "counterparty_name": recognized.get("counterparty_name") or None,
        "counterparty_inn": recognized.get("counterparty_inn") or None,
        "counterparty_kpp": recognized.get("counterparty_kpp") or None,
        "counterparty_account": recognized.get("counterparty_account") or None,
        "raw_operation": operation.raw_operation,
    }


def _direction(value: str) -> str:
    if value == "Приход":
        return "income"
    if value == "Расход":
        return "expense"
    return "unknown"
