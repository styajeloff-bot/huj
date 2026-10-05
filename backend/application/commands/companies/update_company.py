
"""``PUT /api/v1/companies/{id}`` — update an accessible company.

Access is gated by the same ownership rule as the read path: owners
(``users.company_id`` or ``user_companies``) and ``carcraft_employee``
may update ordinary fields; everyone else gets 403. The ``is_active``
field, including an explicitly supplied ``null``, is reserved for
``carcraft_employee``. INN uniqueness is re-checked against other rows
(excluding the current company).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.commands.companies.deactivate_company import (
    deactivate_company_safely,
)
from application.common import _isoformat
from domain.entities.company import Company
from domain.errors import (
    CompanyAccessDeniedError,
    CompanyAlreadyExistsError,
    CompanyNotFoundError,
    InvalidCompanyPayloadError,
    InvalidInnError,
)
from infrastructure.messaging.dwh_events import emit_company_changed
from infrastructure.repositories import company_repository as repo

_INN_RE = re.compile(r"^\d{10}$|^\d{12}$")


@dataclass(frozen=True)
class UpdateCompanyCommand:
    company_id: UUID
    actor_id: UUID
    actor_role: str | None
    data: dict[str, Any] = field(default_factory=dict)
    clear_null_fields: frozenset[str] = field(default_factory=frozenset)
    emit_event: bool = True


def build_company_changed_event(
    company_id: UUID, updated: dict[str, Any]
) -> dict[str, Any]:
    """Build the company.changed payload from the final company snapshot."""
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


def _ensure_activation_allowed(cmd: UpdateCompanyCommand) -> None:
    if "is_active" in cmd.data and cmd.actor_role != "carcraft_employee":
        raise CompanyAccessDeniedError(
            "Изменение статуса компании доступно только сотрудникам Carcraft"
        )


async def _apply_activation_request(
    session: AsyncSession,
    company_id: UUID,
    requested: bool | None,
) -> dict[str, Any] | None:
    if requested is False:
        return await deactivate_company_safely(
            session,
            company_id,
            reject_if_inactive=False,
        )
    if requested is not True:
        return None
    locked = await repo.lock_company_for_deactivation(session, company_id)
    if locked is None:
        raise CompanyNotFoundError()
    if locked.get("is_active") is True:
        return dict(locked)
    reactivated = await repo.reactivate_company(session, company_id)
    return dict(reactivated) if reactivated is not None else None


async def _apply_mutable_payload(
    session: AsyncSession,
    company_id: UUID,
    payload: dict[str, Any],
    current: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if payload:
        result = await repo.update_company(session, company_id, payload)
        return dict(result) if result is not None else None
    if current is not None:
        return current
    result = await repo.get_company_by_id(session, company_id)
    return dict(result) if result is not None else None


async def _ensure_valid_unique_inn(
    session: AsyncSession, company_id: UUID, inn: Any
) -> None:
    if inn is None:
        return
    if not _INN_RE.match(str(inn)):
        raise InvalidInnError(str(inn))
    other_id = await repo.find_company_id_by_inn(session, str(inn))
    if other_id is not None and other_id != company_id:
        raise CompanyAlreadyExistsError(str(inn))


async def handle_update_company(
    cmd: UpdateCompanyCommand, session: AsyncSession
) -> dict[str, Any]:
    existing = await repo.get_company_by_id(session, cmd.company_id)
    if existing is None:
        raise CompanyNotFoundError()

    # Ownership gate — reuses the domain-level ensure_owned_by rule.
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

    _ensure_activation_allowed(cmd)

    payload = {
        key: value
        for key, value in cmd.data.items()
        if value is not None
        or key
        in {
            "kpp",
            "ogrn",
            "legal_address",
            "actual_address",
            "website",
        }
        or key in cmd.clear_null_fields
    }
    can_manage_dealer_groups = payload.pop("can_manage_dealer_groups", None)
    activation_requested = payload.pop("is_active", None)
    if can_manage_dealer_groups is not None and cmd.actor_role != "carcraft_employee":
        raise CompanyAccessDeniedError()

    await _ensure_valid_unique_inn(session, cmd.company_id, payload.get("inn"))

    updated = await _apply_activation_request(
        session, cmd.company_id, activation_requested
    )
    updated = await _apply_mutable_payload(
        session, cmd.company_id, payload, updated
    )
    if updated is None:
        raise InvalidCompanyPayloadError("Не удалось обновить компанию")
    if can_manage_dealer_groups is not None:
        if updated.get("company_type") != "distributor":
            raise InvalidCompanyPayloadError(
                "Право управления группами дилеров доступно только дистрибьютору"
            )
        await repo.set_distributor_dealer_group_permission(
            session,
            cmd.company_id,
            can_manage_dealer_groups=bool(can_manage_dealer_groups),
        )
        refreshed = await repo.get_company_by_id(session, cmd.company_id)
        if refreshed is not None:
            updated = refreshed
    if updated.get("company_type") == "distributor":
        distributor = await repo.get_distributor_extension(session, cmd.company_id)
        updated = dict(updated)
        updated["distributor"] = distributor
    if cmd.emit_event:
        emit_company_changed(build_company_changed_event(cmd.company_id, updated))
    return {
        "message": "Компания успешно обновлена",
        "company": dict(updated),
    }
