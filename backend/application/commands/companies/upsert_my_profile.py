
"""``POST /api/v1/companies/profile`` — upsert the current user's company.

Mirrors Express's ``POST /api/companies/profile``: if the user is already
linked to a company (``users.company_id``) we update it in place; otherwise
a new company row is created and attached to the user. For
``leasing_company`` / ``distributor`` types the one-to-one extension row
is also ensured.

Role-dependent access isn't enforced here — any authenticated user may
create/update their own company. The handler does, however, check INN
uniqueness against other companies (excluding the caller's).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.common import _isoformat
from domain.errors import (
    CompanyAlreadyExistsError,
    InvalidCompanyPayloadError,
    InvalidCompanyTypeError,
    InvalidInnError,
)
from infrastructure.messaging.dwh_events import emit_company_changed
from infrastructure.repositories import (
    admin_companies_repository as admin_repo,
)
from infrastructure.repositories import (
    company_repository as repo,
)

_INN_RE = re.compile(r"^\d{10}$|^\d{12}$")
_ALLOWED_TYPES: frozenset[str] = frozenset(
    {"dealer", "leasing_company", "distributor", "other"}
)


@dataclass(frozen=True)
class UpsertMyCompanyProfileCommand:
    user_id: UUID
    data: dict[str, Any] = field(default_factory=dict)


def _validate_payload(payload: dict[str, Any]) -> tuple[str, str]:
    inn = payload.get("inn")
    if not inn or not _INN_RE.match(str(inn)):
        raise InvalidInnError(str(inn) if inn else None)
    company_type = payload.get("company_type")
    if not company_type or company_type not in _ALLOWED_TYPES:
        raise InvalidCompanyTypeError(company_type)
    if not payload.get("name"):
        raise InvalidCompanyPayloadError("Поле 'name' обязательно")
    return str(inn), str(company_type)


async def _create_company_for_user(
    session: AsyncSession,
    user_id: UUID,
    payload: dict[str, Any],
    *,
    inn: str,
    company_type: str,
) -> UUID:
    company_id: UUID = await admin_repo.create_company(
        session,
        name=str(payload.get("name") or ""),
        inn=inn,
        kpp=payload.get("kpp"),
        ogrn=payload.get("ogrn"),
        company_type=company_type,
        legal_address=payload.get("legal_address"),
        phone=payload.get("phone"),
        email=payload.get("email"),
        full_name=payload.get("full_name"),
        short_name=payload.get("short_name"),
        legal_address_details=None,
        founders=None,
        additional_okved_list=None,
        main_okved_code=None,
        main_okved_description=None,
        director_full_name=None,
        director_position=None,
        enrichment_status="not_enriched",
    )
    extras = {
        k: v for k, v in payload.items() if k in {"actual_address", "website"}
    }
    if extras:
        await repo.update_company(session, company_id, extras)
    await repo.attach_user_to_company(session, user_id, company_id)
    return company_id


async def _ensure_extension(
    session: AsyncSession, company_id: UUID, company_type: str
) -> None:
    if company_type == "leasing_company":
        existing = await repo.get_leasing_company_extension(session, company_id)
        if existing is None:
            await admin_repo.create_leasing_company(
                session, company_id=company_id
            )
    elif company_type == "distributor":
        existing_dist = await repo.get_distributor_extension(
            session, company_id
        )
        if existing_dist is None:
            await admin_repo.create_distributor(
                session, company_id=company_id
            )


async def handle_upsert_my_company_profile(
    cmd: UpsertMyCompanyProfileCommand, session: AsyncSession
) -> dict[str, Any]:
    payload = dict(cmd.data)
    if "is_active" in payload:
        raise InvalidCompanyPayloadError(
            "Поле is_active нельзя изменять напрямую; используйте DELETE компании"
        )
    inn, company_type = _validate_payload(payload)

    current_company_id = await repo.get_user_company_id(session, cmd.user_id)

    existing_id_by_inn = await repo.find_company_id_by_inn(session, inn)
    if (
        existing_id_by_inn is not None
        and existing_id_by_inn != current_company_id
    ):
        raise CompanyAlreadyExistsError(inn)

    if current_company_id is not None:
        old_company = await repo.get_company_by_id(session, current_company_id)
        updated = await repo.update_company(
            session, current_company_id, payload
        )
        if updated is None:
            raise InvalidCompanyPayloadError("Не удалось обновить профиль")
        company_id = current_company_id
        if old_company is not None:
            from infrastructure.messaging.status_events import (
                emit_company_status_changed,
            )
            for field in ("enrichment_status",):
                old_val = old_company.get(field)
                new_val = payload.get(field)
                if new_val is not None and old_val != new_val:
                    emit_company_status_changed(
                        company_id=company_id,
                        field=field,
                        old_value=old_val,
                        new_value=new_val,
                        changed_by=cmd.user_id,
                    )
    else:
        company_id = await _create_company_for_user(
            session,
            cmd.user_id,
            payload,
            inn=inn,
            company_type=company_type,
        )

    await _ensure_extension(session, company_id, company_type)

    result = await repo.get_company_by_id(session, company_id)
    if result is None:
        raise InvalidCompanyPayloadError("Компания не найдена после сохранения")
    emit_company_changed({
        "company_id": company_id,
        "name": result.get("name"),
        "inn": result.get("inn"),
        "kpp": result.get("kpp"),
        "ogrn": result.get("ogrn"),
        "company_type": result.get("company_type"),
        "address": result.get("address"),
        "contact_info": result.get("contact_info"),
        "legal_address": result.get("legal_address"),
        "actual_address": result.get("actual_address"),
        "phone": result.get("phone"),
        "email": result.get("email"),
        "website": result.get("website"),
        "is_active": result.get("is_active"),
        "full_name": result.get("full_name"),
        "short_name": result.get("short_name"),
        "okpo": result.get("okpo"),
        "okato": result.get("okato"),
        "legal_form": result.get("legal_form"),
        "region": result.get("region"),
        "city": result.get("city"),
        "registration_date": _isoformat(result.get("registration_date")),
        "employees_count": result.get("employees_count"),
        "main_okved_code": result.get("main_okved_code"),
        "main_okved_description": result.get("main_okved_description"),
        "director_full_name": result.get("director_full_name"),
        "bank_bik": result.get("bank_bik"),
        "bank_name": result.get("bank_name"),
        "authorized_capital": result.get("authorized_capital"),
        "net_profit": result.get("net_profit"),
        "reporting_year": result.get("reporting_year"),
        "tax_system": result.get("tax_system"),
        "enrichment_status": result.get("enrichment_status"),
        "created_at": _isoformat(result.get("created_at")),
        "updated_at": _isoformat(result.get("updated_at")),
        "_deleted": False,
    })
    return {
        "message": "Профиль компании успешно сохранён",
        "company_id": company_id,
        "company": dict(result),
    }
