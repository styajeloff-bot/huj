"""Application-layer per-row company upsert for the async CSV import pipeline.

Extracted from the companies router so the taskiq worker can reuse it. Adds
``city`` / ``region`` / ``actual_address`` capture (needed by the warehouse and
sales-by-region distributor dashboards). Bulk import runs without external
enrichment (``lookup_provider=None``) — no DaData calls in the worker.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.commands.admin_companies import (
    CreateCompanyCommand,
    handle_create_company,
)
from application.commands.companies import (
    UpdateCompanyCommand,
    handle_update_company,
)
from application.queries.companies import find_company_by_id, find_company_id_by_inn

_UPDATE_FIELDS = (
    "kpp",
    "ogrn",
    "legal_address",
    "actual_address",
    "city",
    "region",
    "phone",
    "email",
    "website",
    "director_full_name",
    "director_position",
    "director_inn",
    "bank_name",
    "bank_bik",
    "bank_account_number",
    "tax_system",
)
_NULLABLE_FIELDS = {"kpp", "ogrn", "legal_address", "actual_address", "website"}


def _parse_uuid(value: str | None) -> UUID | None:
    raw = (value or "").strip()
    if not raw:
        return None
    try:
        return UUID(raw)
    except ValueError:
        return None


async def _resolve_existing_company_id(
    session: AsyncSession, company_id: UUID | None, inn: str
) -> UUID | None:
    if company_id is not None and await find_company_by_id(session, company_id):
        return company_id
    if inn:
        return await find_company_id_by_inn(session, inn)
    return None


def _build_update_data(
    name: str, inn: str, company_type: str, row: dict[str, str]
) -> dict[str, Any]:
    data: dict[str, Any] = {}
    if name:
        data["name"] = name
    if inn:
        data["inn"] = inn
    if company_type:
        data["company_type"] = company_type
    for field in _UPDATE_FIELDS:
        value = (row.get(field) or "").strip()
        if value:
            data[field] = value
        elif field in _NULLABLE_FIELDS:
            data[field] = None
    return data


async def upsert_company_row(
    session: AsyncSession,
    *,
    actor_id: UUID,
    actor_role: str | None,
    row: dict[str, str],
) -> tuple[str, str | None]:
    """Upsert one company CSV row. Returns ``(action, error)``."""
    company_id = _parse_uuid(row.get("id"))
    name = (row.get("name") or "").strip()
    inn = (row.get("inn") or "").strip()
    company_type = (row.get("company_type") or "").strip()
    if not name or not company_type:
        return ("error", "пропущены обязательные поля name/company_type")

    existing_id = await _resolve_existing_company_id(session, company_id, inn)

    if existing_id is not None:
        await handle_update_company(
            UpdateCompanyCommand(
                company_id=existing_id,
                actor_id=actor_id,
                actor_role=actor_role,
                data=_build_update_data(name, inn, company_type, row),
            ),
            session,
        )
        return ("updated", None)

    created = await handle_create_company(
        CreateCompanyCommand(
            inn=inn or "0000000000",
            company_type=company_type,
            name=name,
            kpp=(row.get("kpp") or "").strip() or None,
            ogrn=(row.get("ogrn") or "").strip() or None,
            legal_address=(row.get("legal_address") or "").strip() or None,
            actual_address=(row.get("actual_address") or "").strip() or None,
            city=(row.get("city") or "").strip() or None,
            region=(row.get("region") or "").strip() or None,
            phone=(row.get("phone") or "").strip() or None,
            email=(row.get("email") or "").strip() or None,
            company_id=company_id,
        ),
        session,
        None,
    )
    # The create command/repo carry only a subset of columns. Backfill the
    # remaining advertised CSV columns (website, director_*, bank_*, tax_system)
    # through the update path so a FIRST import emits the full denormalized
    # company to the DWH, identical to the update path.
    extra = _build_update_data(name, inn, company_type, row)
    if created and created.get("id") is not None:
        await handle_update_company(
            UpdateCompanyCommand(
                company_id=created["id"],
                actor_id=actor_id,
                actor_role=actor_role,
                data=extra,
            ),
            session,
        )
    return ("created", None)
