"""Shared guard for company address persistence."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

_COMPANY_ADDRESS_FIELDS = ("legal_address", "actual_address")


def ensure_company_addresses_are_not_blank(values: Mapping[str, Any]) -> None:
    """Reject empty strings while preserving omitted and nullable addresses."""
    for field in _COMPANY_ADDRESS_FIELDS:
        value = values.get(field)
        if isinstance(value, str) and not value.strip():
            raise ValueError(f"{field} cannot be blank")
