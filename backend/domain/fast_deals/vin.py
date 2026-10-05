"""VIN normalisation and validation for fast deal positions."""
from __future__ import annotations

import re

from domain.fast_deals.errors import FastDealValidationError

# 17 symbols, no I, O, Q. The catalog accepts a wider format; that global
# contract is deliberately not narrowed: only registration applies this rule.
_VIN = re.compile(r"^[A-HJ-NPR-Z0-9]{17}$")


def normalize_vin(value: str | None) -> str:
    return (value or "").strip().upper()


def validate_vin(value: str | None, *, field: str = "vin") -> str:
    vin = normalize_vin(value)
    if not vin:
        raise FastDealValidationError("Укажите VIN", field=field)
    if not _VIN.fullmatch(vin):
        raise FastDealValidationError(
            "VIN должен состоять из 17 символов: латинские буквы без I, O, Q и цифры",
            field=field,
        )
    return vin


def is_valid_vin(value: str | None) -> bool:
    return bool(_VIN.fullmatch(normalize_vin(value)))
