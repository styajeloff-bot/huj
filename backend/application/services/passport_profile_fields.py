from __future__ import annotations

from datetime import date, datetime
from typing import Any

PASSPORT_MAIN_TYPE = "ceo_passport_page23"
PASSPORT_REGISTRATION_TYPE = "ceo_passport_registration"


def extract_fields(record: dict[str, Any] | None) -> dict[str, Any]:
    if not record:
        return {}
    raw = record.get("raw_data")
    if not isinstance(raw, dict):
        return {}
    items = raw.get("items")
    if not isinstance(items, list) or not items:
        return {}
    first = items[0]
    if not isinstance(first, dict):
        return {}
    fields = first.get("fields")
    return fields if isinstance(fields, dict) else {}


def first_text(fields: Any, *keys: str) -> str:
    if not isinstance(fields, dict):
        return ""
    for key in keys:
        value = fields.get(key)
        if isinstance(value, dict):
            value = value.get("text") or value.get("value")
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def normalize_gender(value: Any) -> str | None:
    text = str(value or "").strip().lower()
    if not text:
        return None
    text = text.replace(".", "")
    male_values = {"м", "m", "male", "man", "муж", "мужской"}
    female_values = {"ж", "f", "female", "woman", "жен", "женский"}
    if text in male_values:
        return "male"
    if text in female_values:
        return "female"
    return None


def gender_label(value: Any) -> str:
    gender = normalize_gender(value)
    if gender == "male":
        return "Мужской"
    if gender == "female":
        return "Женский"
    return ""


def first_gender(fields: Any) -> str | None:
    text = first_text(
        fields,
        "gender",
        "sex",
        "пол",
        "gender_text",
        "sex_text",
    )
    return normalize_gender(text)


def full_name_from_fields(fields: Any) -> str | None:
    surname = first_text(fields, "surname", "last_name")
    first_name = first_text(fields, "first_name", "name")
    middle_name = first_text(fields, "other_names", "middle_name", "patronymic")
    full_name = " ".join(part for part in (surname, first_name, middle_name) if part)
    return full_name or None


def parse_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value or "").strip()
    parsed: date | None = None
    if text:
        try:
            parsed = date.fromisoformat(text)
        except ValueError:
            separator = "." if "." in text else "/" if "/" in text else ""
            parts = text.split(separator) if separator else []
            if len(parts) == 3 and all(part.isdigit() for part in parts):
                day, month, year = parts
                try:
                    parsed = date(int(year), int(month), int(day))
                except ValueError:
                    parsed = None
    return parsed


def profile_autofill_from_passport_records(
    *,
    main: dict[str, Any] | None,
    registration: dict[str, Any] | None,
) -> dict[str, Any]:
    main_fields = extract_fields(main)
    registration_fields = extract_fields(registration)
    birth_date = parse_date(first_text(main_fields, "birth_date", "date_of_birth"))
    passport_issued_date = parse_date(first_text(main_fields, "date_of_issue"))
    address = first_text(
        registration_fields,
        "address",
        "unrestricted_value",
        "address_gar",
        "registration_address",
    )

    payload: dict[str, Any] = {}
    if birth_date is not None:
        payload["birth_date"] = birth_date
    if passport_issued_date is not None:
        payload["passport_issued_date"] = passport_issued_date
    gender = first_gender(main_fields)
    if gender is not None:
        payload["gender"] = gender
    full_name = full_name_from_fields(main_fields)
    if full_name is not None:
        payload["full_name"] = full_name
    passport_series = first_text(main_fields, "series_and_number", "series_number")
    if passport_series:
        payload["passport_series"] = passport_series
    passport_issued_by = first_text(main_fields, "issuing_authority")
    if passport_issued_by:
        payload["passport_issued_by"] = passport_issued_by
    if address:
        payload["address"] = address
    return payload
