
"""Create company (admin) command with optional external enrichment."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.common import _isoformat
from application.errors import ServiceError
from domain.errors import (
    CompanyAlreadyExistsError,
    CompanyLookupUnavailableError,
    InvalidCompanyTypeError,
    InvalidInnError,
)
from domain.services.company_lookup import CompanyLookupProvider
from infrastructure.messaging.dwh_events import emit_company_changed
from infrastructure.repositories import admin_companies_repository as repo

ALLOWED_COMPANY_TYPES: frozenset[str] = frozenset(
    {"dealer", "leasing_company", "distributor", "other"}
)

_INN_RE = re.compile(r"^\d{10}$|^\d{12}$")


@dataclass
class CreateCompanyCommand:
    inn: str
    company_type: str
    name: str | None = None
    kpp: str | None = None
    ogrn: str | None = None
    legal_address: str | None = None
    phone: str | None = None
    email: str | None = None
    company_id: UUID | None = None
    city: str | None = None
    region: str | None = None
    actual_address: str | None = None


def _validate_inn(inn: str) -> None:
    if not inn or not _INN_RE.match(inn):
        raise InvalidInnError(inn)


async def handle_create_company(
    cmd: CreateCompanyCommand,
    session: AsyncSession,
    lookup_provider: CompanyLookupProvider | None = None,
) -> dict[str, Any]:
    _validate_inn(cmd.inn)

    if cmd.company_type not in ALLOWED_COMPANY_TYPES:
        raise InvalidCompanyTypeError(cmd.company_type)

    if await repo.inn_exists(session, cmd.inn):
        raise CompanyAlreadyExistsError(cmd.inn)

    # Optional external enrichment — soft failure (continue with client-provided
    # name if provider unavailable).
    enrichment: dict[str, Any] = {}
    enrichment_status = "not_enriched"
    if lookup_provider is not None:
        try:
            matches = await lookup_provider.search(cmd.inn, limit=1)
        except CompanyLookupUnavailableError:
            matches = []
        if matches:
            info = matches[0]
            enrichment = {
                "full_name": info.full_name,
                "short_name": info.name,
                "legal_address_details": (
                    {"raw": info.legal_address}
                    if info.legal_address
                    else None
                ),
                "main_okved_description": info.business_activity,
                "director_full_name": info.manager_name,
            }
            enrichment_status = "enriched"

    name = (cmd.name or "").strip() or (
        enrichment.get("short_name") or enrichment.get("full_name") or cmd.inn
    )

    company_id = await repo.create_company(
        session,
        name=name,
        inn=cmd.inn,
        kpp=cmd.kpp,
        ogrn=cmd.ogrn,
        company_type=cmd.company_type,
        legal_address=cmd.legal_address,
        phone=cmd.phone,
        email=cmd.email,
        full_name=enrichment.get("full_name"),
        short_name=enrichment.get("short_name"),
        legal_address_details=enrichment.get("legal_address_details"),
        founders=None,
        additional_okved_list=None,
        main_okved_code=None,
        main_okved_description=enrichment.get("main_okved_description"),
        director_full_name=enrichment.get("director_full_name"),
        director_position=None,
        enrichment_status=enrichment_status,
        company_id=cmd.company_id,
        city=cmd.city,
        region=cmd.region,
        actual_address=cmd.actual_address,
    )
    from infrastructure.messaging.status_events import emit_company_status_changed
    emit_company_status_changed(
        company_id=company_id,
        field="enrichment_status",
        old_value=None,
        new_value=enrichment_status,
    )

    if cmd.company_type == "leasing_company":
        await repo.create_leasing_company(session, company_id=company_id)
    elif cmd.company_type == "distributor":
        await repo.create_distributor(session, company_id=company_id)

    saved = await repo.get_by_id(session, company_id)
    if saved is None:
        raise ServiceError("Не удалось создать запись")
    emit_company_changed({
        "company_id": company_id,
        "name": saved.get("name"),
        "inn": saved.get("inn"),
        "kpp": saved.get("kpp"),
        "ogrn": saved.get("ogrn"),
        "company_type": saved.get("company_type"),
        "address": saved.get("address"),
        "contact_info": saved.get("contact_info"),
        "legal_address": saved.get("legal_address"),
        "actual_address": saved.get("actual_address"),
        "phone": saved.get("phone"),
        "email": saved.get("email"),
        "website": saved.get("website"),
        "is_active": saved.get("is_active"),
        "full_name": saved.get("full_name"),
        "short_name": saved.get("short_name"),
        "okpo": saved.get("okpo"),
        "okato": saved.get("okato"),
        "legal_form": saved.get("legal_form"),
        "region": saved.get("region"),
        "city": saved.get("city"),
        "registration_date": _isoformat(saved.get("registration_date")),
        "employees_count": saved.get("employees_count"),
        "main_okved_code": saved.get("main_okved_code"),
        "main_okved_description": saved.get("main_okved_description"),
        "director_full_name": saved.get("director_full_name"),
        "bank_bik": saved.get("bank_bik"),
        "bank_name": saved.get("bank_name"),
        "authorized_capital": saved.get("authorized_capital"),
        "net_profit": saved.get("net_profit"),
        "reporting_year": saved.get("reporting_year"),
        "tax_system": saved.get("tax_system"),
        "enrichment_status": saved.get("enrichment_status"),
        "created_at": _isoformat(saved.get("created_at")),
        "updated_at": _isoformat(saved.get("updated_at")),
        "_deleted": False,
    })
    return cast("dict[str, Any]", saved)
