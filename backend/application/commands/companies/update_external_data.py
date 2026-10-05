
"""``PUT /api/v1/companies/{id}/external-data`` — refresh enrichment fields.

Express's Company1C flow wrote to a separate ``company_1c_data`` table;
after migration 010 those fields live inline on ``companies``. This
command therefore writes directly to the company row but only accepts
the enrichment-field subset — never touches ``name`` / ``company_type`` /
``is_active`` to avoid drift from the admin surface.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.common import _isoformat
from domain.entities.company import Company
from domain.errors import (
    CompanyHasNoInnError,
    CompanyNotFoundError,
    InvalidCompanyPayloadError,
)
from infrastructure.messaging.dwh_events import emit_company_changed
from infrastructure.repositories import company_repository as repo


@dataclass(frozen=True)
class UpdateCompanyExternalDataCommand:
    company_id: UUID
    actor_id: UUID
    actor_role: str | None
    data: dict[str, Any] = field(default_factory=dict)


async def handle_update_company_external_data(
    cmd: UpdateCompanyExternalDataCommand, session: AsyncSession
) -> dict[str, Any]:
    existing = await repo.get_company_by_id(session, cmd.company_id)
    if existing is None:
        raise CompanyNotFoundError()

    entity = Company.from_dict(dict(existing))
    if cmd.actor_role == "carcraft_employee":
        entity.ensure_owned_by(
            user_id=cmd.actor_id,
            user_role=cmd.actor_role,
            user_company_id=None,
        )
    else:
        primary_company_id = await repo.get_user_company_id(
            session, cmd.actor_id
        )
        linked_ids = await repo.list_user_company_ids(session, cmd.actor_id)
        entity.ensure_owned_by(
            user_id=cmd.actor_id,
            user_role=cmd.actor_role,
            user_company_id=primary_company_id,
            user_company_ids=linked_ids,
        )

    if not await repo.company_has_inn(session, cmd.company_id):
        raise CompanyHasNoInnError()

    updated = await repo.update_company_external_data(
        session, cmd.company_id, dict(cmd.data)
    )
    if updated is None:
        raise InvalidCompanyPayloadError("Не удалось обновить данные компании")
    emit_company_changed({
        "company_id": cmd.company_id,
        "name": updated.get("name"),
        "inn": updated.get("inn"),
        "kpp": updated.get("kpp"),
        "ogrn": updated.get("ogrn"),
        "company_type": updated.get("company_type"),
        "address": updated.get("address"),
        "contact_info": updated.get("contact_info"),
        "legal_address": updated.get("legal_address"),
        "actual_address": updated.get("actual_address"),
        "phone": updated.get("phone"),
        "email": updated.get("email"),
        "website": updated.get("website"),
        "is_active": updated.get("is_active"),
        "full_name": updated.get("full_name"),
        "short_name": updated.get("short_name"),
        "okpo": updated.get("okpo"),
        "okato": updated.get("okato"),
        "legal_form": updated.get("legal_form"),
        "region": updated.get("region"),
        "city": updated.get("city"),
        "registration_date": _isoformat(updated.get("registration_date")),
        "employees_count": updated.get("employees_count"),
        "main_okved_code": updated.get("main_okved_code"),
        "main_okved_description": updated.get("main_okved_description"),
        "director_full_name": updated.get("director_full_name"),
        "bank_bik": updated.get("bank_bik"),
        "bank_name": updated.get("bank_name"),
        "authorized_capital": updated.get("authorized_capital"),
        "net_profit": updated.get("net_profit"),
        "reporting_year": updated.get("reporting_year"),
        "tax_system": updated.get("tax_system"),
        "enrichment_status": updated.get("enrichment_status"),
        "created_at": _isoformat(updated.get("created_at")),
        "updated_at": _isoformat(updated.get("updated_at")),
        "_deleted": False,
    })
    return {
        "message": "Данные компании успешно обновлены",
        "data": dict(updated),
    }
