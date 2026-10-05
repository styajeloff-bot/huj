"""Parser for 1CClientBankExchange text bank statements."""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from domain.services.bank_statements.errors import BankStatementParseError
from domain.services.bank_statements.models import (
    ParsedBankAccountSection,
    ParsedBankOperation,
    ParsedBankStatement,
)


def parse_bank_statement(data: bytes) -> ParsedBankStatement:
    text, encoding = _decode(data)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines or lines[0] != "1CClientBankExchange":
        raise BankStatementParseError(
            "Файл не является банковской выпиской. Проверьте содержимое файла"
        )

    header: dict[str, Any] = {}
    accounts: list[ParsedBankAccountSection] = []
    operations: list[ParsedBankOperation] = []
    index = 1
    while index < len(lines):
        line = lines[index]
        if line == "СекцияРасчСчет":
            section, index = _collect_block(lines, index + 1, "КонецРасчСчет")
            accounts.append(_account_section(section))
            continue
        if line.startswith("СекцияДокумент="):
            document_section = line.split("=", 1)[1]
            section, index = _collect_block(lines, index + 1, "КонецДокумента")
            operations.append(_operation(document_section, section))
            continue
        key, value = _split(line)
        header[key] = value
        index += 1

    return ParsedBankStatement(
        encoding=encoding,
        format_version=_empty_to_none(header.get("ВерсияФормата")),
        sender=_empty_to_none(header.get("Отправитель")),
        recipient=_empty_to_none(header.get("Получатель")),
        created_on=_date(header.get("ДатаСоздания")),
        period_start=_date(header.get("ДатаНачала")),
        period_end=_date(header.get("ДатаКонца")),
        statement_account=_empty_to_none(header.get("РасчСчет")),
        accounts=accounts,
        operations=operations,
        raw_header=header,
    )


def _decode(data: bytes) -> tuple[str, str]:
    if not data:
        raise BankStatementParseError("Файл пуст")
    for encoding in ("utf-8-sig", "cp1251"):
        try:
            return data.decode(encoding), ("utf-8-sig" if encoding == "utf-8-sig" else "cp1251")
        except UnicodeDecodeError:
            continue
    raise BankStatementParseError(
        "Файл не является банковской выпиской. Проверьте содержимое файла"
    )


def _split(line: str) -> tuple[str, str | None]:
    if "=" not in line:
        return line, None
    key, value = line.split("=", 1)
    return key, value if value != "" else None


def _collect_block(
    lines: list[str], index: int, terminator: str
) -> tuple[dict[str, Any], int]:
    out: dict[str, Any] = {}
    while index < len(lines):
        line = lines[index]
        if line == terminator:
            return out, index + 1
        key, value = _split(line)
        out[key] = value
        index += 1
    raise BankStatementParseError(
        "Файл не является банковской выпиской. Проверьте содержимое файла"
    )


def _empty_to_none(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return str(value)


def _date(value: Any) -> date | None:
    text = _empty_to_none(value)
    if text is None:
        return None
    try:
        day, month, year = text.split(".")
        return date(int(year), int(month), int(day))
    except ValueError as exc:
        raise BankStatementParseError("Некорректная дата в банковской выписке") from exc


def _decimal(value: Any) -> Decimal | None:
    text = _empty_to_none(value)
    if text is None:
        return None
    try:
        return Decimal(text.replace(",", "."))
    except InvalidOperation as exc:
        raise BankStatementParseError("Некорректная сумма в банковской выписке") from exc


def _int(value: Any) -> int | None:
    text = _empty_to_none(value)
    if text is None:
        return None
    try:
        return int(text)
    except ValueError as exc:
        raise BankStatementParseError("Некорректное число в банковской выписке") from exc


def _account_section(raw: dict[str, Any]) -> ParsedBankAccountSection:
    return ParsedBankAccountSection(
        account_number=_empty_to_none(raw.get("РасчСчет")),
        period_start=_date(raw.get("ДатаНачала")),
        period_end=_date(raw.get("ДатаКонца")),
        opening_balance=_decimal(raw.get("НачальныйОстаток")),
        total_income=_decimal(raw.get("ВсегоПоступило")),
        total_expense=_decimal(raw.get("ВсегоСписано")),
        closing_balance=_decimal(raw.get("КонечныйОстаток")),
        raw_section=raw,
    )


def _operation(document_section: str, raw: dict[str, Any]) -> ParsedBankOperation:
    amount = _decimal(raw.get("Сумма"))
    if amount is None:
        raise BankStatementParseError("Некорректная сумма в банковской выписке")
    return ParsedBankOperation(
        document_section=document_section,
        document_number=_empty_to_none(raw.get("Номер")),
        document_date=_date(raw.get("Дата")),
        amount=amount,
        payer_account=_empty_to_none(raw.get("ПлательщикСчет")),
        payer_correspondent=_empty_to_none(raw.get("ПлательщикКорсчет")),
        payer_write_off_date=_date(raw.get("ДатаСписано")),
        payer_inn=_empty_to_none(raw.get("ПлательщикИНН")),
        payer_name=_empty_to_none(raw.get("Плательщик1") or raw.get("Плательщик")),
        payer_bank_name=_empty_to_none(raw.get("ПлательщикБанк1")),
        payer_bik=_empty_to_none(raw.get("ПлательщикБИК")),
        payer_kpp=_empty_to_none(raw.get("ПлательщикКПП")),
        recipient_account=_empty_to_none(raw.get("ПолучательСчет")),
        recipient_receipt_date=_date(raw.get("ДатаПоступило")),
        recipient_inn=_empty_to_none(raw.get("ПолучательИНН")),
        recipient_name=_empty_to_none(raw.get("Получатель1") or raw.get("Получатель")),
        recipient_bank_name=_empty_to_none(raw.get("ПолучательБанк1")),
        recipient_bik=_empty_to_none(raw.get("ПолучательБИК")),
        recipient_kpp=_empty_to_none(raw.get("ПолучательКПП")),
        recipient_correspondent=_empty_to_none(raw.get("ПолучательКорсчет")),
        payment_type=_empty_to_none(raw.get("ВидПлатежа")),
        payment_code=_empty_to_none(raw.get("ВидОплаты")),
        priority=_int(raw.get("Очередность")),
        payment_purpose=_empty_to_none(raw.get("НазначениеПлатежа")),
        raw_operation=raw,
    )
