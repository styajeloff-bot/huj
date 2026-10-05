"""Sync company fields from an application questionnaire.

When a user edits company details in the checkout questionnaire (Step 3),
those changes should be reflected on the parent companies row so that
Step 2 (company profile display) and other consumers of the company
profile see the up-to-date values.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.repositories import company_repository as company_repo

# questionnaire field -> companies column
_QUESTIONNAIRE_TO_COMPANY: dict[str, str] = {
    "full_company_name": "full_name",
    "short_company_name": "short_name",
    "inn": "inn",
    "ogrn": "ogrn",
    "kpp": "kpp",
    "legal_address": "legal_address",
    "actual_address": "actual_address",
    "phone": "phone",
    "email": "email",
    "website": "website",
    "tax_system": "tax_system",
}


async def sync_company_from_questionnaire(
    session: AsyncSession,
    application_id: uuid.UUID,
    questionnaire_payload: dict[str, Any],
    company_id: uuid.UUID | None,
) -> None:
    """Apply overlapping questionnaire fields to the linked companies row."""
    del application_id
    if company_id is None:
        return

    company_updates: dict[str, Any] = {}

    for q_field, c_field in _QUESTIONNAIRE_TO_COMPANY.items():
        value = questionnaire_payload.get(q_field)
        if value is None:
            continue
        if c_field in {"legal_address", "actual_address"} and (
            isinstance(value, str) and not value.strip()
        ):
            continue
        company_updates[c_field] = value

    # name is required on companies — keep it in sync with the full name
    if questionnaire_payload.get("full_company_name"):
        company_updates["name"] = questionnaire_payload["full_company_name"]
    elif questionnaire_payload.get("short_company_name"):
        company_updates["name"] = questionnaire_payload["short_company_name"]

    if not company_updates:
        return

    await company_repo.update_company(session, company_id, company_updates)
