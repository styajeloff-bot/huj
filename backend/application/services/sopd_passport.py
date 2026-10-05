"""Server-only mapping and validation for SOPD passport snapshots."""

from __future__ import annotations

import re
from contextlib import suppress
from datetime import UTC, date, datetime
from math import isfinite
from typing import Any

from application.services.passport_profile_fields import (
    first_gender,
    first_text,
    parse_date,
)

FIELDS = (
    "surname",
    "name",
    "patronymic",
    "nationality",
    "gender",
    "birthDate",
    "birthPlace",
    "passportSeries",
    "passportNumber",
    "givenDate",
    "code",
    "givenWhom",
)
RU_NATIONALITIES = frozenset(
    {
        "рф",
        "россия",
        "российскаяфедерация",
        "российскойфедерации",
        "гражданинроссийскойфедерации",
        "гражданкароссийскойфедерации",
    }
)


def country_code(nationality: Any) -> str | None:
    value = re.sub(r"[.\s]+", "", str(nationality or "").casefold())
    return "RU" if value in RU_NATIONALITIES else ("FOREIGN" if value else None)


def _value(raw: Any) -> str | None:
    if isinstance(raw, dict):
        raw = raw.get("text") or raw.get("value")
    value = str(raw or "").strip()
    return value or None


def _iso_date(raw: Any) -> str | None:
    """Return only a real ISO calendar date; never expose DBrain's raw value."""
    value = _value(raw)
    parsed = parse_date(value)
    if parsed is None and value is not None:
        with suppress(ValueError):
            parsed = datetime.strptime(value, "%d-%m-%Y").replace(tzinfo=UTC).date()
    return parsed.isoformat() if parsed is not None else None


def _confidence_value(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    numeric = float(value)
    if not isfinite(numeric) or not 0 <= numeric <= 1:
        return None
    return round(numeric * 100)


def _field_confidence(
    fields: dict[str, Any], confidence: Any, *sources: str
) -> int | None:
    if isinstance(confidence, dict):
        for source in sources:
            value = _confidence_value(confidence.get(source))
            if value is not None:
                return value
    for source in sources:
        entry = fields.get(source)
        if isinstance(entry, dict):
            value = _confidence_value(entry.get("confidence"))
            if value is not None:
                return value
    return None


def map_dbrain(raw: dict[str, Any]) -> tuple[dict[str, Any], dict[str, int]]:
    items = raw.get("items") if isinstance(raw, dict) else None
    item = (
        items[0]
        if isinstance(items, list) and items and isinstance(items[0], dict)
        else {}
    )
    fields = item.get("fields", {})
    fields = fields if isinstance(fields, dict) else {}
    confidence_raw = item.get("confidence")
    aliases = {
        "surname": ("surname",),
        "name": ("first_name",),
        "patronymic": ("other_names",),
        "nationality": ("nationality",),
        "birthPlace": ("place_of_birth",),
        "givenDate": ("date_of_issue",),
        "code": ("subdivision_code",),
        "givenWhom": ("issuing_authority",),
    }
    mapped: dict[str, Any] = dict.fromkeys(FIELDS)
    mapped.update(
        {key: first_text(fields, *sources) or None for key, sources in aliases.items()}
    )
    mapped["birthDate"] = _iso_date(first_text(fields, "date_of_birth", "birth_date"))
    mapped["givenDate"] = _iso_date(fields.get("date_of_issue"))
    mapped["gender"] = first_gender(fields)
    series_number = _value(fields.get("series_and_number")) or ""
    parts = re.findall(r"[A-Za-zА-Яа-я0-9]+", series_number)
    if len(parts) >= 2:
        mapped["passportSeries"], mapped["passportNumber"] = (
            parts[0],
            "".join(parts[1:]),
        )
    elif parts:
        mapped["passportSeries"], mapped["passportNumber"] = None, parts[0]
    confidence: dict[str, int] = {}
    confidence_sources = {
        **aliases,
        "gender": ("sex", "gender", "пол"),
        "birthDate": ("date_of_birth", "birth_date"),
    }
    for key, sources in confidence_sources.items():
        value = _field_confidence(fields, confidence_raw, *sources)
        if value is not None:
            confidence[key] = value
    series_confidence = _field_confidence(fields, confidence_raw, "series_and_number")
    if series_confidence is not None:
        confidence["passportSeries"] = series_confidence
        confidence["passportNumber"] = series_confidence
    return mapped, confidence


def validate(
    fields: dict[str, Any], recognition: dict[str, Any], *, expected_full_name: Any = None
) -> None:
    values = {key: fields.get(key) for key in FIELDS}
    if values["givenWhom"] is not None and len(str(values["givenWhom"])) > 250:
        raise PassportValidationError(
            "PASSPORT_RU_FORMAT_INVALID",
            "Значение поля «Кем выдан» не может быть длиннее 250 символов.",
            {"givenWhom": "PASSPORT_RU_FORMAT_INVALID"},
        )
    nationality = country_code(values["nationality"])
    if nationality is None:
        raise PassportValidationError(
            "PASSPORT_NATIONALITY_REQUIRED",
            "Необходимо указать гражданство.",
            {"nationality": "PASSPORT_NATIONALITY_REQUIRED"},
        )
    required = (
        FIELDS
        if nationality == "RU"
        else ("surname", "name", "nationality", "birthDate", "gender", "passportNumber")
    )
    missing = {
        key: "PASSPORT_FIELDS_REQUIRED"
        for key in required
        if values.get(key) is None or not str(values[key]).strip()
    }
    if missing:
        raise PassportValidationError(
            "PASSPORT_FIELDS_REQUIRED", "Заполните обязательные поля паспорта.", missing
        )
    # An OCR snapshot is validated exclusively against the immutable OCR name
    # and the candidate name captured before upload.  Manual field values must
    # neither substitute OCR data nor trigger an OCR comparison.
    if _full_name_from_fields(recognition):
        _validate_name(
            expected_full_name or recognition.get("_expected_full_name"), recognition
        )
    for key in ("birthDate", "givenDate"):
        if values.get(key):
            try:
                date.fromisoformat(str(values[key]))
            except ValueError:
                raise PassportValidationError(
                    "PASSPORT_RU_FORMAT_INVALID",
                    "Укажите реальную дату в формате YYYY-MM-DD.",
                    {key: "PASSPORT_RU_FORMAT_INVALID"},
                ) from None
    if nationality != "RU":
        too_long = {
            key: "PASSPORT_RU_FORMAT_INVALID"
            for key, value in values.items()
            if key != "givenWhom" and value is not None and len(str(value)) > 30
        }
        if too_long:
            raise PassportValidationError(
                "PASSPORT_RU_FORMAT_INVALID",
                "Значение документа не может быть длиннее 30 символов.",
                too_long,
            )
        return
    _validate_ru(values)


def _validate_ru(values: dict[str, Any]) -> None:
    invalid = {}
    for key in ("passportSeries", "passportNumber"):
        if not re.fullmatch(r"\d{1,10}", str(values[key])):
            invalid[key] = "PASSPORT_RU_FORMAT_INVALID"
    if not re.fullmatch(r"\d{3}-\d{3}", str(values["code"])):
        invalid["code"] = "PASSPORT_RU_FORMAT_INVALID"
    if invalid:
        raise PassportValidationError(
            "PASSPORT_RU_FORMAT_INVALID",
            "Неверный формат российского паспорта.",
            invalid,
        )
def _validate_name(expected: Any, fields: dict[str, Any]) -> None:
    expected_name = _normal_full_name(expected)
    actual_name = _full_name_from_fields(fields)
    if expected_name and actual_name and expected_name != actual_name:
        raise PassportValidationError(
            "PASSPORT_NAME_MISMATCH",
            "ФИО в распознанном паспорте не совпадает с ФИО кандидата на момент загрузки.",
            {"surname": "PASSPORT_NAME_MISMATCH"},
        )


def _normal_full_name(value: Any) -> str:
    return " ".join(str(value or "").casefold().replace("ё", "е").split())


def _full_name_from_fields(fields: dict[str, Any]) -> str:
    return _normal_full_name(
        " ".join(str(fields.get(key) or "") for key in ("surname", "name", "patronymic"))
    )


class PassportValidationError(Exception):
    def __init__(self, code: str, message: str, fields: dict[str, str]):
        self.code, self.message, self.fields = code, message, fields
