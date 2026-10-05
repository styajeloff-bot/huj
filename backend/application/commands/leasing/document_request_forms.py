"""Strict, allow-listed contracts for Bitrix #20418 document forms."""
from __future__ import annotations

import re
from typing import Any

_DIGITS = re.compile(r"^[0-9]+$")


def validate_form_data(schema: dict[str, Any], value: Any) -> dict[str, Any]:
    if not isinstance(schema, dict) or not isinstance(value, dict):
        raise ValueError("form_data должен быть JSON-объектом")  # noqa: TRY004 - invalid user payload maps to HTTP 422
    kind = schema.get("kind")
    if kind == "main_counterparties":
        return {"counterparties": _counterparties(value)}
    if kind == "open_bank_accounts":
        return {"accounts": _accounts(value, schema.get("schema_version"))}
    if kind == "beneficial_owner":
        if set(value) != {"fio"} or not isinstance(value["fio"], str) or not value["fio"].strip():
            raise ValueError("Требуется непустое ФИО выгодоприобретателя")
        return {"fio": value["fio"].strip()}
    if kind == "snils":
        if set(value) != {"number"} or not isinstance(value["number"], str):
            raise ValueError("Требуется СНИЛС")
        number = value["number"]
        if not _DIGITS.fullmatch(number) or len(number) != 11:
            raise ValueError("СНИЛС должен содержать 11 цифр")
        return {"number": number}
    raise ValueError("Неподдерживаемая схема формы")


def _counterparties(value: dict[str, Any]) -> list[dict[str, str]]:
    if set(value) != {"counterparties"} or not isinstance(value["counterparties"], list) or not 1 <= len(value["counterparties"]) <= 10:
        raise ValueError("Требуется от 1 до 10 контрагентов")
    result = []
    for item in value["counterparties"]:
        if (
            not isinstance(item, dict)
            or not {"name", "inn"} <= item.keys()
            or item.keys() - {"name", "inn", "comment"}
            or not isinstance(item["name"], str)
            or not item["name"].strip()
            or not isinstance(item["inn"], str)
            or len(item["inn"]) not in (10, 12)
            or not _DIGITS.fullmatch(item["inn"])
        ):
            raise ValueError("У контрагента обязательны название и ИНН из 10 или 12 цифр")
        comment = item.get("comment")
        if comment is not None and not isinstance(comment, str):
            raise ValueError("Комментарий контрагента должен быть текстом")
        counterparty = {"name": item["name"].strip(), "inn": item["inn"]}
        if isinstance(comment, str) and comment.strip():
            counterparty["comment"] = comment.strip()
        result.append(counterparty)
    return result


def _accounts(value: dict[str, Any], version: Any) -> list[dict[str, Any]]:
    # A request keeps the catalog schema it was created with. Historical answers
    # stay in that version; never invent a correspondent account for v1.
    if type(version) is not int or version not in (1, 2):
        raise ValueError("Неподдерживаемая версия формы расчётных счетов")
    if set(value) != {"accounts"} or not isinstance(value["accounts"], list) or not 1 <= len(value["accounts"]) <= 10:
        raise ValueError("Требуется от 1 до 10 расчётных счетов")
    return [_account(item, version) for item in value["accounts"]]


def _account(item: Any, version: int) -> dict[str, Any]:
    if not isinstance(item, dict):
        raise ValueError("Некорректный расчётный счёт")  # noqa: TRY004 - invalid request payload maps to HTTP 422
    if version == 1:
        if set(item) != {"bank", "acc_number"} or not isinstance(item["bank"], dict) or set(item["bank"]) != {"name", "bik"}:
            raise ValueError("Некорректный расчётный счёт")
        bank_name, bik = item["bank"]["name"], item["bank"]["bik"]
    else:
        if set(item) != {"bank", "bik", "acc_number", "correspondent_account"}:
            raise ValueError("Укажите наименование банка, расчётный счёт, БИК и корреспондентский счёт")
        bank_name, bik = item["bank"], item["bik"]
    if not isinstance(bank_name, str) or not bank_name.strip():
        raise ValueError("Укажите наименование банка")
    if not _exact_digits(bik, 9) or not _exact_digits(item["acc_number"], 20):
        raise ValueError("БИК должен содержать 9 цифр, счёт — 20 цифр")
    if version == 1:
        return {"bank": {"name": bank_name.strip(), "bik": bik}, "acc_number": item["acc_number"]}
    if not _exact_digits(item["correspondent_account"], 20):
        raise ValueError("Корреспондентский счёт должен содержать 20 цифр")
    return {
        "bank": bank_name.strip(), "bik": bik, "acc_number": item["acc_number"],
        "correspondent_account": item["correspondent_account"],
    }


def _exact_digits(value: Any, length: int) -> bool:
    return isinstance(value, str) and len(value) == length and bool(_DIGITS.fullmatch(value))
