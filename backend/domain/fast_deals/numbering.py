"""Immutable human number: ``DD-<INN>-<DDMMYY>-<NNN>`` / ``DL-...``.

The date is the UTC day of creation. The sequence has at least three digits and is
never truncated after 999. Ordinary application numbers are not affected.
"""
from __future__ import annotations

import re
from datetime import date

from domain.fast_deals.errors import FastDealValidationError
from domain.fast_deals.values import NUMBER_PREFIX, SourceType

_NUMBER = re.compile(r"^(DD|DL)-(\d+)-(\d{6})-(\d{3,})$")


def number_prefix(source_type: SourceType | str, inn: str, day: date) -> str:
    """``DD-7707083893-051026-`` — the part shared by one day of one client."""
    source = SourceType(source_type)
    return f"{NUMBER_PREFIX[source]}-{inn}-{day:%d%m%y}-"


def format_number(source_type: SourceType | str, inn: str, day: date, sequence: int) -> str:
    if sequence < 1:
        raise ValueError("Номер сделки начинается с 001")
    return f"{number_prefix(source_type, inn, day)}{sequence:03d}"


def lock_key(source_type: SourceType | str, inn: str, day: date) -> str:
    """Advisory transaction lock key: direction, client INN and the whole day."""
    return f"fast_deal_display_number:{SourceType(source_type).value}:{inn}:{day:%Y-%m-%d}"


def sequence_of(display_number: str) -> int | None:
    match = _NUMBER.fullmatch(display_number)
    return int(match.group(4)) if match else None


def normalize_client_inn(inn: str | None) -> str:
    value = (inn or "").strip()
    if not re.fullmatch(r"\d{10}|\d{12}", value):
        raise FastDealValidationError(
            "У клиента должен быть корректный ИНН (10 или 12 цифр)", field="company"
        )
    return value
