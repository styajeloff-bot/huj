"""Persistence helpers for native auth registration and company linking.

Enrichment data (formerly in `company_1c_data`) lives directly on
`companies` as explicit, named columns. No raw JSONB blob is kept —
everything is normalized on write.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any, TypedDict
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.models.companies import Company
from infrastructure.models.positions import Position
from infrastructure.models.users import CompanySelectHistory, User, UserCompany
from infrastructure.repositories.company_address_guard import (
    ensure_company_addresses_are_not_blank,
)
from infrastructure.repositories.dadata_normalization import normalize_dadata_payload
from infrastructure.repository_timing import timed_repository


class CompanyPayload(TypedDict, total=False):
    name: str
    full_name: str | None
    inn: str
    kpp: str | None
    ogrn: str | None
    legal_address: str | None
    actual_address: str | None
    phone: str | None
    email: str | None
    manager_name: str | None
    entity_type: str | None
    foundation_date: str | None
    employee_count: int | None
    business_activity: str | None
    website: str | None


def _resolve_company_type(entity_type: str | None) -> str:
    if entity_type == "dealer":
        return "dealer"
    if entity_type == "leasing_company":
        return "leasing_company"
    if entity_type == "distributor":
        return "distributor"
    return "other"


def _build_contact_info(payload: CompanyPayload) -> dict[str, Any]:
    return {
        "annual_revenue": None,
        "employee_count": payload.get("employee_count"),
        "foundation_date": payload.get("foundation_date"),
        "business_activity": payload.get("business_activity"),
        "bank_name": None,
        "account_number": None,
        "bic": None,
        "manager_name": payload.get("manager_name"),
    }


@timed_repository
async def get_company_by_inn(session: AsyncSession, inn: str) -> dict[str, Any] | None:
    result = await session.execute(sa.select(Company).where(Company.inn == inn))
    company = result.scalars().first()
    if not company:
        return None
    return {"id": company.id, "name": company.name, "inn": company.inn}


@timed_repository
async def create_company_from_payload(
    session: AsyncSession, payload: CompanyPayload
) -> dict[str, Any]:
    ensure_company_addresses_are_not_blank(payload)
    company = Company(
        name=payload.get("name") or payload.get("full_name") or payload["inn"],
        inn=payload["inn"],
        kpp=payload.get("kpp"),
        ogrn=payload.get("ogrn"),
        company_type=_resolve_company_type(payload.get("entity_type")),
        full_name=payload.get("full_name"),
        legal_address=payload.get("legal_address"),
        actual_address=payload.get("actual_address"),
        phone=payload.get("phone"),
        email=payload.get("email"),
        website=payload.get("website"),
        contact_info=_build_contact_info(payload),
        is_active=True,
        enrichment_status="pending",
    )
    session.add(company)
    await session.flush()
    await session.refresh(company)
    return {"id": company.id, "name": company.name, "inn": company.inn}


@timed_repository
async def create_or_get_company(
    session: AsyncSession, payload: CompanyPayload
) -> dict[str, Any] | None:
    inn = payload.get("inn")
    if not inn:
        return None
    existing = await get_company_by_inn(session, inn)
    if existing:
        existing["is_new"] = False
        return existing
    company = await create_company_from_payload(session, payload)
    company["is_new"] = True
    return company


@timed_repository
async def insert_user_companies(
    session: AsyncSession, user_id: UUID, company_ids: list[UUID]
) -> None:
    for company_id in company_ids:
        session.add(UserCompany(user_id=user_id, company_id=company_id))
    await session.flush()


@timed_repository
async def insert_user_company_links(
    session: AsyncSession,
    user_id: UUID,
    links: list[tuple[UUID, str | None, bool, bool]],
) -> None:
    """Insert user-company links with sub-role and permissions.

    Each tuple is (company_id, sub_role, can_view_applications, can_create_applications).
    """
    for company_id, sub_role, can_view, can_create in links:
        session.add(
            UserCompany(
                user_id=user_id,
                company_id=company_id,
                sub_role=sub_role,
                can_view_applications=can_view,
                can_create_applications=can_create,
            )
        )
    await session.flush()


@timed_repository
async def ensure_user_company_link(
    session: AsyncSession, user_id: UUID, company_id: UUID
) -> None:
    """Idempotently add ``(user_id, company_id)`` to user_companies.

    Safe to call repeatedly — duplicates are skipped via ON CONFLICT DO NOTHING.
    Used by the invite flow: we might re-invite the same founder before the
    application is submitted, and bumping into the composite primary key
    shouldn't abort the request.
    """
    stmt = (
        pg_insert(UserCompany)
        .values(user_id=user_id, company_id=company_id)
        .on_conflict_do_nothing(index_elements=["user_id", "company_id"])
    )
    await session.execute(stmt)
    await session.flush()


@timed_repository
async def set_primary_company_if_absent(
    session: AsyncSession, user_id: UUID, company_id: UUID
) -> None:
    """Set a user's primary company once without replacing an existing choice."""
    await session.execute(
        sa.update(User)
        .where(User.id == user_id, User.company_id.is_(None))
        .values(company_id=company_id)
    )
    await session.flush()


@timed_repository
async def list_user_companies(
    session: AsyncSession, user_id: UUID
) -> list[dict[str, Any]]:
    """Return active companies linked to the user via user_companies OR
    users.company_id (legacy primary), deduplicated and ordered by name.

    Includes sub_role and permission flags from user_companies (fallback to
    administrator with full access for legacy primary-only links).
    """
    via_join = sa.select(UserCompany.company_id).where(
        UserCompany.user_id == user_id,
        sa.or_(UserCompany.is_active.is_(True), UserCompany.is_active.is_(None)),
    )
    via_primary = sa.select(User.company_id).where(
        User.id == user_id, User.company_id.is_not(None)
    )
    stmt = (
        sa.select(
            Company.id,
            Company.name,
            Company.inn,
            UserCompany.user_id.label("linked_user_id"),
            UserCompany.role,
            UserCompany.sub_role,
            UserCompany.can_view_applications,
            UserCompany.can_create_applications,
            UserCompany.position_id,
            UserCompany.is_active,
            Position.name.label("position_name"),
        )
        .outerjoin(
            UserCompany,
            sa.and_(
                UserCompany.company_id == Company.id,
                UserCompany.user_id == user_id,
            ),
        )
        .outerjoin(
            Position,
            UserCompany.position_id == Position.id,
        )
        .where(
            Company.is_active.is_(True),
            sa.or_(UserCompany.is_active.is_(True), UserCompany.is_active.is_(None)),
            sa.or_(Company.id.in_(via_join), Company.id.in_(via_primary)),
        )
        .order_by(Company.name)
    )
    result = await session.execute(stmt)
    rows = []
    for r in result.all():
        has_join_row = r.linked_user_id is not None
        if has_join_row:
            role = r.role or "client"
            sub_role = r.sub_role or "employee"
            can_view = bool(r.can_view_applications)
            can_create = bool(r.can_create_applications)
            position_id = str(r.position_id) if r.position_id else None
            position_name = r.position_name
            is_active = bool(r.is_active) if r.is_active is not None else True
        else:
            role = "client"
            sub_role = "administrator"
            can_view = True
            can_create = True
            position_id = None
            position_name = None
            is_active = True
        rows.append(
            {
                "id": r.id,
                "name": r.name,
                "inn": r.inn,
                "role": role,
                "sub_role": sub_role,
                "can_view_applications": can_view,
                "can_create_applications": can_create,
                "position_id": position_id,
                "position_name": position_name,
                "is_active": is_active,
            }
        )
    return rows


@timed_repository
async def get_company_permissions(
    session: AsyncSession, user_id: UUID, company_id: UUID
) -> dict[str, Any]:
    """Return permission dict for a user in a specific company.

    Falls back to ``administrator`` with full access when no ``user_companies``
    row exists (legacy users who only have ``users.company_id``).
    """
    result = await session.execute(
        sa.select(
            UserCompany.is_active,
            UserCompany.role,
            UserCompany.sub_role,
            UserCompany.can_view_applications,
            UserCompany.can_create_applications,
            UserCompany.position_id,
        ).where(
            UserCompany.user_id == user_id,
            UserCompany.company_id == company_id,
        )
    )
    row = result.one_or_none()
    if row is None:
        legacy = await session.execute(
            sa.select(User.company_id, User.role).where(
                User.id == user_id,
                User.company_id == company_id,
            )
        )
        legacy_row = legacy.one_or_none()
        if legacy_row is None:
            return {
                "sub_role": None,
                "can_view_applications": False,
                "can_create_applications": False,
                "role": None,
                "position_id": None,
                "is_active": False,
            }
        return {
            "role": legacy_row.role or "client",
            "sub_role": "administrator",
            "can_view_applications": True,
            "can_create_applications": True,
            "position_id": None,
            "is_active": True,
        }
    if row.is_active is False:
        return {
            "sub_role": None,
            "can_view_applications": False,
            "can_create_applications": False,
            "role": row.role,
            "position_id": str(row.position_id) if row.position_id else None,
            "is_active": False,
        }
    return {
        "role": row.role or "client",
        "sub_role": row.sub_role or "employee",
        "can_view_applications": bool(row.can_view_applications),
        "can_create_applications": bool(row.can_create_applications),
        "position_id": str(row.position_id) if row.position_id else None,
        "is_active": True if row.is_active is None else bool(row.is_active),
    }


@timed_repository
async def get_company_select_history(
    session: AsyncSession, user_id: UUID
) -> dict[str, Any] | None:
    """Return ``{company_id, updated_at}`` or ``None`` if no row exists."""
    row = await session.get(CompanySelectHistory, user_id)
    if row is None:
        return None
    return {"company_id": row.company_id, "updated_at": row.updated_at}


@timed_repository
async def upsert_company_select_history(
    session: AsyncSession, user_id: UUID, company_id: UUID
) -> None:
    uc = await session.execute(
        sa.select(UserCompany.is_active).where(
            UserCompany.user_id == user_id,
            UserCompany.company_id == company_id,
        )
    )
    is_active_val = uc.scalar_one_or_none()
    if is_active_val is False:
        raise ValueError(f"Company link {company_id} for user {user_id} is inactive")
    if is_active_val is None:
        legacy = await session.execute(
            sa.select(User.company_id).where(
                User.id == user_id,
                User.company_id == company_id,
            )
        )
        if legacy.scalar_one_or_none() is None:
            raise ValueError(f"Company {company_id} is not linked to user {user_id}")

    existing = await session.get(CompanySelectHistory, user_id)
    now = datetime.now(UTC).replace(tzinfo=None)
    if existing:
        existing.company_id = company_id
        existing.updated_at = now  # type: ignore[assignment]
    else:
        session.add(
            CompanySelectHistory(user_id=user_id, company_id=company_id, updated_at=now)
        )
    await session.flush()


@timed_repository
async def _get_company_row(session: AsyncSession, inn: str) -> Company | None:
    result = await session.execute(sa.select(Company).where(Company.inn == inn))
    return result.scalars().first()


@timed_repository
async def create_or_update_pending_enrichment(session: AsyncSession, inn: str) -> None:
    company = await _get_company_row(session, inn)
    if not company:
        return
    if company.enrichment_status == "success":
        return
    company.enrichment_status = "pending"
    company.enrichment_last_error = None
    await session.flush()


@timed_repository
async def mark_enrichment_fetching(session: AsyncSession, inn: str) -> None:
    company = await _get_company_row(session, inn)
    if not company:
        return
    company.enrichment_status = "fetching"
    company.enrichment_last_error = None
    await session.flush()


@timed_repository
async def mark_enrichment_failed(
    session: AsyncSession, inn: str, error_message: str
) -> None:
    company = await _get_company_row(session, inn)
    if not company:
        return
    attempts = int(company.enrichment_attempts or 0) + 1
    company.enrichment_status = "failed"
    company.enrichment_attempts = attempts
    company.enrichment_last_error = error_message
    company.enrichment_last_fetch_at = datetime.now(UTC)  # type: ignore[assignment]
    await session.flush()


def _normalize_enrichment_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Flatten the nested 1C ``CounterpartyByNN`` response.

    The 1C service returns data nested under ``data.{company_info,management,
    bank_info,activity_codes,financial_info,registration_info,founders}``;
    ``save_enrichment_data`` expects a flat dict.
    """
    data: dict[str, Any] = payload.get("data") or {}
    company_info: dict[str, Any] = data.get("company_info") or {}
    management: dict[str, Any] = data.get("management") or {}
    director: dict[str, Any] = management.get("director") or {}
    bank_info: dict[str, Any] = data.get("bank_info") or {}
    activity: dict[str, Any] = data.get("activity_codes") or {}
    main_okved_list = activity.get("main_okved") or []
    additional_okved_list = activity.get("additional_okved") or []
    main_okved = main_okved_list[0] if main_okved_list else {}
    additional_first = additional_okved_list[0] if additional_okved_list else {}
    financial: dict[str, Any] = data.get("financial_info") or {}
    registration: dict[str, Any] = data.get("registration_info") or {}
    founders = data.get("founders")

    reg_date = registration.get("registration_date")
    reg_date_only: date | None = None
    if isinstance(reg_date, str) and reg_date:
        try:
            reg_date_only = date.fromisoformat(reg_date.split("T", 1)[0])
        except ValueError:
            reg_date_only = None

    return {
        "full_name": company_info.get("full_name"),
        "short_name": company_info.get("short_name"),
        "kpp": company_info.get("kpp"),
        "ogrn": company_info.get("ogrn"),
        "okpo": company_info.get("okpo"),
        "okato": company_info.get("okato"),
        "legal_address": company_info.get("legal_address"),
        "legal_address_string": _address_to_string(company_info.get("legal_address")),
        "registration_date": reg_date_only,
        "registration_department": registration.get("registration_department"),
        "employees_count": _safe_int(registration.get("employees_count")),
        "main_okved_code": main_okved.get("code"),
        "main_okved_description": main_okved.get("description"),
        "additional_okved_code": additional_first.get("code"),
        "additional_okved_description": additional_first.get("description"),
        "additional_okved_list": additional_okved_list,
        "director_full_name": director.get("full_name"),
        "director_position": director.get("position"),
        "director_inn": director.get("inn"),
        "founders": founders,
        "bank_bik": bank_info.get("bik"),
        "bank_name": bank_info.get("bank_name"),
        "bank_account_number": bank_info.get("account_number"),
        "region": company_info.get("region"),
        "city": company_info.get("city"),
        "legal_form": company_info.get("legal_form"),
        "authorized_capital": _safe_int(financial.get("authorized_capital")),
        "net_profit": _safe_int(financial.get("net_profit")),
        "reporting_year": _safe_int(financial.get("reporting_year")),
        "website": company_info.get("website"),
    }


def _address_to_string(legal_address: Any) -> str | None:
    if not legal_address:
        return None
    if isinstance(legal_address, str):
        return legal_address
    if isinstance(legal_address, dict):
        value = legal_address.get("value")
        if isinstance(value, str) and value:
            return value
    return None


def _safe_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _apply_enrichment_fields(company: Company, normalized: dict[str, Any]) -> None:
    company.full_name = normalized["full_name"]
    company.short_name = normalized["short_name"]
    company.kpp = normalized["kpp"] or company.kpp
    company.ogrn = normalized["ogrn"] or company.ogrn
    company.okpo = normalized["okpo"]
    company.okato = normalized["okato"]
    company.legal_address_details = normalized["legal_address"]
    legal_address = normalized["legal_address_string"]
    if isinstance(legal_address, str) and legal_address.strip():
        company.legal_address = legal_address
    company.registration_date = normalized["registration_date"]
    company.registration_department = normalized["registration_department"]
    company.employees_count = normalized["employees_count"]
    company.main_okved_code = normalized["main_okved_code"]
    company.main_okved_description = normalized["main_okved_description"]
    company.additional_okved_code = normalized["additional_okved_code"]
    company.additional_okved_description = normalized["additional_okved_description"]
    company.additional_okved_list = normalized["additional_okved_list"]
    company.director_full_name = normalized["director_full_name"]
    company.director_position = normalized["director_position"]
    company.director_inn = normalized["director_inn"]
    company.founders = normalized["founders"]
    company.bank_bik = normalized["bank_bik"]
    company.bank_name = normalized["bank_name"]
    company.bank_account_number = normalized["bank_account_number"]
    company.region = normalized["region"]
    company.city = normalized["city"]
    company.legal_form = normalized["legal_form"]
    company.authorized_capital = normalized["authorized_capital"]
    company.net_profit = normalized["net_profit"]
    company.reporting_year = normalized["reporting_year"]
    company.website = normalized["website"] or company.website
    company.tax_system = normalized.get("tax_system")
    company.enrichment_status = "success"
    company.enrichment_attempts = int(company.enrichment_attempts or 0) + 1
    company.enrichment_last_error = None
    company.enrichment_last_fetch_at = datetime.now(UTC)  # type: ignore[assignment]


@timed_repository
async def save_enrichment_data(
    session: AsyncSession,
    inn: str,
    payload: dict[str, Any],
    *,
    _company_id: UUID | None,
) -> None:
    company = await _get_company_row(session, inn)
    if not company:
        return

    status = payload.get("status")
    if status not in (None, "success"):
        raise ValueError(f"Unexpected enrichment payload status: {status}")

    normalized = _normalize_enrichment_payload(payload)
    _apply_enrichment_fields(company, normalized)
    await session.flush()


@timed_repository
async def save_dadata_enrichment(
    session: AsyncSession, inn: str, dadata_data: dict[str, Any]
) -> None:
    """Normalize and persist a raw DaData ``data`` block."""
    company = await _get_company_row(session, inn)
    if not company:
        return

    normalized = normalize_dadata_payload(dadata_data)
    _apply_enrichment_fields(company, normalized)
    await session.flush()
