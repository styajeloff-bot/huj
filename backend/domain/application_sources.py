"""Application origin is fixed at creation; number prefixes are display metadata."""

from __future__ import annotations

import re
from typing import Literal

from domain.errors import ApplicationNotSubmittableError

ApplicationCreationSource = Literal["platform", "dealer_site", "distributor_site"]
APPLICATION_SOURCES = frozenset({"platform", "dealer_site", "distributor_site"})
SOURCE_VIEW_ROLES = frozenset({"carcraft_employee", "leasing_company", "distributor", "dealer"})
_SOURCE_PREFIXES = {"AP": "platform", "ADE": "dealer_site", "ADI": "distributor_site"}


def source_for_creation(requested: str, warehouse_owner_type: str | None) -> str:
    if requested == "platform":
        return "platform"
    if requested not in APPLICATION_SOURCES:
        raise ApplicationNotSubmittableError("Недопустимый источник заявки")
    if warehouse_owner_type == "dealer":
        return "dealer_site"
    if warehouse_owner_type == "distributor":
        return "distributor_site"
    raise ApplicationNotSubmittableError(
        "Не удалось определить владельца склада первого товара для источника заявки"
    )


def source_filter_values(raw: str | None) -> tuple[str, ...]:
    if raw is None or not raw.strip():
        return ()
    values = tuple(dict.fromkeys(value.strip() for value in raw.split(",")))
    if any(value not in APPLICATION_SOURCES for value in values):
        raise ApplicationNotSubmittableError("Недопустимый фильтр источника заявки")
    return values


def parse_application_number_search(raw: str) -> tuple[str, str | None, str]:
    """Keep ordinary search text and normalize only numeric application numbers."""
    text = raw.strip()
    match = re.match(r"^(ADE|ADI|AP)(?=\s*\d|\s*$)\s*(.*)$", text, re.IGNORECASE)
    source = _SOURCE_PREFIXES[match.group(1).upper()] if match else None
    number = match.group(2).strip() if match else text
    digits = re.sub(r"\D", "", number) if re.fullmatch(r"[\d\s./_-]+", number) else ""
    return number, source, digits
