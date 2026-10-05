"""``DELETE /api/v1/companies/{id}`` — soft-deactivate a company (employee only).

Deactivation cascades through the active users linked to this company
and the matching ``leasing_companies`` / ``distributors`` extension row.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.common import _isoformat
from domain.errors import (
    CompanyAccessDeniedError,
    CompanyAlreadyDeactivatedError,
    CompanyNotFoundError,
    CompanySpecialEquipmentConflictError,
)
from infrastructure.repositories import (
    company_change_history_repository as history_repo,
)
from infrastructure.repositories import (
    company_repository as repo,
)
from infrastructure.repositories import (
    special_equipment_seller_guard_repository as seller_guard_repo,
)


@dataclass(frozen=True)
class DeactivateCompanyCommand:
    company_id: UUID
    actor_role: str | None
    # Legacy direct callers do not have an authenticated actor. They retain
    # their mutation behavior, but cannot create an unattributable audit row.
    actor_id: UUID | None = None


async def deactivate_company_safely(
    session: AsyncSession,
    company_id: UUID,
    *,
    reject_if_inactive: bool,
) -> dict[str, Any]:
    """Serialize seller validation and the company/user soft-deactivation."""
    existing = await repo.lock_company_for_deactivation(session, company_id)
    if existing is None:
        raise CompanyNotFoundError()

    if existing.get("is_active") is False:
        if reject_if_inactive:
            raise CompanyAlreadyDeactivatedError()
        return dict(existing)

    blockers = await seller_guard_repo.seller_deactivation_blockers(
        session, company_id
    )
    if seller_guard_repo.has_seller_deactivation_blockers(blockers):
        raise CompanySpecialEquipmentConflictError()

    updated = await repo.soft_delete_company(session, company_id)
    if updated is None:
        raise CompanyNotFoundError()
    return dict(updated)


def _company_changed_event(company_id: UUID, updated: dict[str, Any]) -> dict[str, Any]:
    """Build the legacy payload for publication only after the router commits."""
    return {
        "company_id": company_id,
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
    }


async def handle_deactivate_company(
    cmd: DeactivateCompanyCommand, session: AsyncSession
) -> dict[str, Any]:
    if cmd.actor_role != "carcraft_employee":
        raise CompanyAccessDeniedError(
            "Деактивация компании доступна только сотрудникам Carcraft"
        )

    updated = await deactivate_company_safely(
        session,
        cmd.company_id,
        reject_if_inactive=True,
    )
    if cmd.actor_id is not None:
        await history_repo.write_snapshot(
            session, company_id=cmd.company_id, actor_user_id=cmd.actor_id,
            action="company_status_changed",
        )
    return {
        "message": "Компания успешно деактивирована",
        "company": dict(updated),
        "company_changed_event": _company_changed_event(cmd.company_id, updated),
    }
