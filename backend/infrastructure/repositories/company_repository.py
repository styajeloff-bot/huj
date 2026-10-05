"""Company profile repository — returns dicts, never ORM objects.

Responsible for:
  * Fetching a company row by id (with all enrichment columns flattened in).
  * Fetching the optional ``leasing_companies`` / ``distributors`` extension
    row keyed by ``company_id`` (one-to-one).
  * Looking up the user's ``company_id`` (primary link).
  * Listing the user's ``user_companies`` join rows for owner-checks.
  * Listing all companies (paginated, filterable) for admin / self-service
    surfaces.
  * Updating / soft-deleting a company row and refreshing enrichment
    fields (external 1C / DaData data).
  * Computing per-company metrics (users / applications / vehicles).
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any, TypedDict, cast
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.models.applications import LeasingApplication
from infrastructure.models.companies import Company, Distributor, LeasingCompany
from infrastructure.models.special_equipment import SpecialEquipmentProduct
from infrastructure.models.users import User, UserCompany
from infrastructure.repositories.company_address_guard import (
    ensure_company_addresses_are_not_blank,
)
from infrastructure.repository_timing import timed_repository


class CompanyDict(TypedDict, total=False):
    id: UUID
    name: str
    inn: str | None
    kpp: str | None
    ogrn: str | None
    company_type: str
    legal_address: str | None
    actual_address: str | None
    phone: str | None
    email: str | None
    website: str | None
    is_active: bool | None
    full_name: str | None
    short_name: str | None
    okpo: str | None
    okato: str | None
    legal_form: str | None
    region: str | None
    city: str | None
    legal_address_details: dict[str, Any] | None
    registration_date: date | None
    registration_department: str | None
    employees_count: int | None
    main_okved_code: str | None
    main_okved_description: str | None
    additional_okved_code: str | None
    additional_okved_description: str | None
    additional_okved_list: Any
    director_full_name: str | None
    director_position: str | None
    director_inn: str | None
    founders: Any
    bank_bik: str | None
    bank_name: str | None
    bank_account_number: str | None
    authorized_capital: int | None
    net_profit: int | None
    reporting_year: int | None
    enrichment_status: str | None
    tax_system: str | None
    created_at: datetime | None
    updated_at: datetime | None


def _company_to_dict(row: Company) -> CompanyDict:
    return CompanyDict(
        id=row.id,
        name=row.name,
        inn=row.inn,
        kpp=row.kpp,
        ogrn=row.ogrn,
        company_type=row.company_type,
        legal_address=row.legal_address,
        actual_address=row.actual_address,
        phone=row.phone,
        email=row.email,
        website=row.website,
        is_active=row.is_active,
        full_name=row.full_name,
        short_name=row.short_name,
        okpo=row.okpo,
        okato=row.okato,
        legal_form=row.legal_form,
        region=row.region,
        city=row.city,
        legal_address_details=row.legal_address_details,
        registration_date=cast("date | None", row.registration_date),
        registration_department=row.registration_department,
        employees_count=row.employees_count,
        main_okved_code=row.main_okved_code,
        main_okved_description=row.main_okved_description,
        additional_okved_code=row.additional_okved_code,
        additional_okved_description=row.additional_okved_description,
        additional_okved_list=row.additional_okved_list,
        director_full_name=row.director_full_name,
        director_position=row.director_position,
        director_inn=row.director_inn,
        founders=row.founders,
        bank_bik=row.bank_bik,
        bank_name=row.bank_name,
        bank_account_number=row.bank_account_number,
        authorized_capital=row.authorized_capital,
        net_profit=row.net_profit,
        reporting_year=row.reporting_year,
        enrichment_status=row.enrichment_status,
        tax_system=row.tax_system,
        created_at=cast("datetime | None", row.created_at),
        updated_at=cast("datetime | None", row.updated_at),
    )


@timed_repository
async def get_company_by_id(
    session: AsyncSession, company_id: UUID
) -> CompanyDict | None:
    row = await session.get(Company, company_id)
    return _company_to_dict(row) if row else None


@timed_repository
async def get_user_company_id(session: AsyncSession, user_id: UUID) -> UUID | None:
    """Return the user's primary ``company_id`` (or None)."""
    result = await session.execute(sa.select(User.company_id).where(User.id == user_id))
    return result.scalar_one_or_none()


@timed_repository
async def list_user_company_ids(session: AsyncSession, user_id: UUID) -> list[UUID]:
    """Return all company ids linked to the user via ``user_companies``."""
    result = await session.execute(
        sa.select(UserCompany.company_id).where(UserCompany.user_id == user_id)
    )
    return list(result.scalars().all())


@timed_repository
async def get_leasing_company_extension(
    session: AsyncSession, company_id: UUID
) -> dict[str, Any] | None:
    """One-to-one ``leasing_companies`` row for this company, or None."""
    result = await session.execute(
        sa.select(LeasingCompany).where(LeasingCompany.company_id == company_id)
    )
    row = result.scalars().first()
    if not row:
        return None
    return {
        "id": row.id,
        "company_id": row.company_id,
        "average_down_payment_percent": row.average_down_payment_percent,
        "average_lease_term_months": row.average_lease_term_months,
        "average_markup_percent": (
            cast("float", row.average_markup_percent)
            if row.average_markup_percent is not None
            else None
        ),
        "min_down_payment_percent": row.min_down_payment_percent,
        "max_lease_term_months": row.max_lease_term_months,
        "special_offers": row.special_offers,
        "is_active": row.is_active,
    }


@timed_repository
async def get_leasing_company_name(
    session: AsyncSession, leasing_company_id: UUID
) -> str | None:
    """Resolve the human-readable leasing-company name by its extension PK.

    ``leasing_company_id`` is the ``leasing_companies.id`` primary key (as
    stored on ``leasing_company_applications.leasing_company_id``). We join to
    ``companies`` via ``leasing_companies.company_id`` to read ``companies.name``.
    """
    stmt = (
        sa.select(Company.name)
        .join(LeasingCompany, LeasingCompany.company_id == Company.id)
        .where(LeasingCompany.id == leasing_company_id)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


@timed_repository
async def get_distributor_extension(
    session: AsyncSession, company_id: UUID
) -> dict[str, Any] | None:
    """One-to-one ``distributors`` row for this company, or None."""
    result = await session.execute(
        sa.select(Distributor).where(Distributor.company_id == company_id)
    )
    row = result.scalars().first()
    if not row:
        return None
    return {
        "id": row.id,
        "company_id": row.company_id,
        "regions": row.regions,
        "brands": row.brands,
        "is_active": row.is_active,
        "can_manage_dealer_groups": row.can_manage_dealer_groups,
    }


@timed_repository
async def set_distributor_dealer_group_permission(
    session: AsyncSession,
    company_id: UUID,
    *,
    can_manage_dealer_groups: bool,
) -> None:
    result = await session.execute(
        sa.update(Distributor)
        .where(Distributor.company_id == company_id)
        .values(
            can_manage_dealer_groups=can_manage_dealer_groups,
            updated_at=datetime.now(UTC),
        )
    )
    if int(cast("sa.engine.CursorResult", result).rowcount or 0) == 0:
        session.add(
            Distributor(
                company_id=company_id,
                is_active=True,
                can_manage_dealer_groups=can_manage_dealer_groups,
            )
        )
    await session.flush()


# ---------------------------------------------------------------------------
# Listing / stats / mutations (Phase 7a — G4)
# ---------------------------------------------------------------------------

# Plain fields that can be set via PUT /{id} and POST /profile flows.
# ``is_active`` is handled by explicit PUT/DELETE lifecycle operations, never
# this generic allowlist; ``id``/``created_at`` are read-only; JSONB enrichment
# fields are written through the external-data path.
_MUTABLE_COMPANY_FIELDS: frozenset[str] = frozenset(
    {
        "name",
        "inn",
        "kpp",
        "ogrn",
        "company_type",
        "legal_address",
        "actual_address",
        "phone",
        "email",
        "website",
        "full_name",
        "short_name",
        "tax_system",
        "city",
        "region",
        "director_full_name",
        "director_position",
        "director_inn",
        "bank_name",
        "bank_bik",
        "bank_account_number",
    }
)

_ENRICHMENT_FIELDS: frozenset[str] = frozenset(
    {
        "full_name",
        "short_name",
        "kpp",
        "ogrn",
        "okpo",
        "okato",
        "legal_address_details",
        "registration_date",
        "registration_department",
        "employees_count",
        "main_okved_code",
        "main_okved_description",
        "additional_okved_code",
        "additional_okved_description",
        "additional_okved_list",
        "director_full_name",
        "director_position",
        "director_inn",
        "founders",
        "bank_bik",
        "bank_name",
        "bank_account_number",
        "authorized_capital",
        "net_profit",
        "reporting_year",
        "region",
        "city",
        "legal_form",
        "website",
        "enrichment_status",
    }
)


@timed_repository
async def list_companies(
    session: AsyncSession,
    *,
    page: int = 1,
    limit: int = 20,
    search: str | None = None,
    name: str | None = None,
    phone: str | None = None,
    company_type: str | None = None,
    is_active: bool | None = None,
) -> tuple[list[CompanyDict], int]:
    """Paginated directory listing with search/type/active filters."""
    conditions: list[Any] = []
    if search:
        pattern = f"%{search}%"
        conditions.append(
            sa.or_(
                sa.func.coalesce(Company.name, "").ilike(pattern),
                sa.func.coalesce(Company.inn, "").ilike(pattern),
                sa.func.coalesce(Company.email, "").ilike(pattern),
            )
        )
    if name:
        conditions.append(sa.func.coalesce(Company.name, "").ilike(f"%{name}%"))
    if phone:
        conditions.append(sa.func.coalesce(Company.phone, "").ilike(f"%{phone}%"))
    if company_type:
        conditions.append(Company.company_type == company_type)
    if is_active is not None:
        conditions.append(Company.is_active == is_active)

    offset = max(0, (page - 1) * limit)

    total_stmt = sa.select(sa.func.count(Company.id))
    if conditions:
        total_stmt = total_stmt.where(*conditions)
    total = int((await session.execute(total_stmt)).scalar() or 0)

    rows_stmt = (
        sa.select(Company)
        .order_by(Company.created_at.desc().nullslast(), Company.id.desc())
        .limit(limit)
        .offset(offset)
    )
    if conditions:
        rows_stmt = rows_stmt.where(*conditions)
    rows = (await session.execute(rows_stmt)).scalars().all()
    return [_company_to_dict(row) for row in rows], total


@timed_repository
async def list_companies_for_export(
    session: AsyncSession,
    *,
    page: int = 1,
    limit: int = 20,
    search: str | None = None,
    name: str | None = None,
    phone: str | None = None,
    company_type: str | None = None,
    is_active: bool | None = None,
) -> tuple[list[dict[str, Any]], int]:
    """Paginated directory listing with relation counts for CSV export."""
    conditions: list[Any] = []
    if search:
        pattern = f"%{search}%"
        conditions.append(
            sa.or_(
                sa.func.coalesce(Company.name, "").ilike(pattern),
                sa.func.coalesce(Company.inn, "").ilike(pattern),
                sa.func.coalesce(Company.email, "").ilike(pattern),
            )
        )
    if name:
        conditions.append(sa.func.coalesce(Company.name, "").ilike(f"%{name}%"))
    if phone:
        conditions.append(sa.func.coalesce(Company.phone, "").ilike(f"%{phone}%"))
    if company_type:
        conditions.append(Company.company_type == company_type)
    if is_active is not None:
        conditions.append(Company.is_active == is_active)

    offset = max(0, (page - 1) * limit)

    total_stmt = sa.select(sa.func.count(Company.id))
    if conditions:
        total_stmt = total_stmt.where(*conditions)
    total = int((await session.execute(total_stmt)).scalar() or 0)

    users_count_sq = (
        sa.select(sa.func.count(User.id))
        .where(User.company_id == Company.id, User.is_active.is_(True))
        .correlate(Company)
        .scalar_subquery()
    )
    applications_count_sq = (
        sa.select(sa.func.count(LeasingApplication.id))
        .where(LeasingApplication.company_id == Company.id)
        .correlate(Company)
        .scalar_subquery()
    )
    vehicles_count_sq = (
        sa.select(sa.func.count(SpecialEquipmentProduct.id))
        .where(SpecialEquipmentProduct.seller_company_id == Company.id)
        .correlate(Company)
        .scalar_subquery()
    )
    leasing_company_id_sq = (
        sa.select(LeasingCompany.id)
        .where(LeasingCompany.company_id == Company.id)
        .correlate(Company)
        .scalar_subquery()
    )
    distributor_id_sq = (
        sa.select(Distributor.id)
        .where(Distributor.company_id == Company.id)
        .correlate(Company)
        .scalar_subquery()
    )

    rows_stmt = (
        sa.select(
            Company,
            users_count_sq.label("users_count"),
            applications_count_sq.label("applications_count"),
            vehicles_count_sq.label("vehicles_count"),
            leasing_company_id_sq.label("leasing_company_id"),
            distributor_id_sq.label("distributor_id"),
        )
        .order_by(Company.created_at.desc().nullslast(), Company.id.desc())
        .limit(limit)
        .offset(offset)
    )
    if conditions:
        rows_stmt = rows_stmt.where(*conditions)
    rows = (await session.execute(rows_stmt)).all()

    items: list[dict[str, Any]] = []
    for row in rows:
        company_dict: dict[str, Any] = dict(_company_to_dict(row.Company))
        company_dict["users_count"] = row.users_count or 0
        company_dict["applications_count"] = row.applications_count or 0
        company_dict["vehicles_count"] = row.vehicles_count or 0
        company_dict["leasing_company_id"] = row.leasing_company_id
        company_dict["distributor_id"] = row.distributor_id
        items.append(company_dict)

    return items, total


@timed_repository
async def update_company(
    session: AsyncSession,
    company_id: UUID,
    data: dict[str, Any],
) -> CompanyDict | None:
    """Update mutable company fields; returns the refreshed dict or None."""
    payload = {k: v for k, v in data.items() if k in _MUTABLE_COMPANY_FIELDS}
    ensure_company_addresses_are_not_blank(payload)
    if not payload:
        return await get_company_by_id(session, company_id)

    payload["updated_at"] = datetime.now(UTC)
    result = await session.execute(
        sa.update(Company).where(Company.id == company_id).values(**payload)
    )
    await session.flush()
    if int(cast("sa.engine.CursorResult", result).rowcount or 0) == 0:
        return None
    return await get_company_by_id(session, company_id)


@timed_repository
async def lock_company_for_deactivation(
    session: AsyncSession, company_id: UUID
) -> CompanyDict | None:
    """Lock a company before cross-domain deactivation checks.

    Special-equipment product writes take a ``FOR SHARE`` lock on their
    selected seller. Taking the conflicting row lock here makes the blocker
    check and soft-deactivation one serialized operation.
    """
    row = await session.scalar(
        sa.select(Company).where(Company.id == company_id).with_for_update()
    )
    return _company_to_dict(row) if row is not None else None


@timed_repository
async def update_company_external_data(
    session: AsyncSession,
    company_id: UUID,
    data: dict[str, Any],
) -> CompanyDict | None:
    """Update enrichment (1C / DaData) fields on a company row."""
    payload = {k: v for k, v in data.items() if k in _ENRICHMENT_FIELDS}
    if not payload:
        return await get_company_by_id(session, company_id)

    payload["updated_at"] = datetime.now(UTC)
    result = await session.execute(
        sa.update(Company).where(Company.id == company_id).values(**payload)
    )
    await session.flush()
    if int(cast("sa.engine.CursorResult", result).rowcount or 0) == 0:
        return None
    return await get_company_by_id(session, company_id)


@timed_repository
async def soft_delete_company(
    session: AsyncSession, company_id: UUID
) -> CompanyDict | None:
    """Soft-deactivate a company and all its active users."""
    now = datetime.now(UTC)
    company_result = await session.execute(
        sa.update(Company)
        .where(Company.id == company_id, Company.is_active.is_(True))
        .values(is_active=False, updated_at=now)
    )
    await session.flush()
    if int(cast("sa.engine.CursorResult", company_result).rowcount or 0) == 0:
        existing = await session.get(Company, company_id)
        if existing is None:
            return None
        # Already deactivated — return the current dict.
        return _company_to_dict(existing)

    # Deactivate downstream users; typed sub-row is_active flags follow.
    await session.execute(
        sa.update(User)
        .where(User.company_id == company_id)
        .values(is_active=False, updated_at=now)
    )
    await session.execute(
        sa.update(LeasingCompany)
        .where(LeasingCompany.company_id == company_id)
        .values(is_active=False, updated_at=now)
    )
    await session.execute(
        sa.update(Distributor)
        .where(Distributor.company_id == company_id)
        .values(is_active=False, updated_at=now)
    )
    await session.flush()
    return await get_company_by_id(session, company_id)


@timed_repository
async def reactivate_company(
    session: AsyncSession, company_id: UUID
) -> CompanyDict | None:
    """Reactivate only the company row through an explicit lifecycle write.

    Users and typed company extensions are intentionally not bulk-reactivated:
    their individual inactive states may have independent administrative
    reasons and must be restored through their own workflows.
    """
    now = datetime.now(UTC)
    result = await session.execute(
        sa.update(Company)
        .where(Company.id == company_id, Company.is_active.is_not(True))
        .values(is_active=True, updated_at=now)
    )
    await session.flush()
    if int(cast("sa.engine.CursorResult", result).rowcount or 0) == 0:
        return await get_company_by_id(session, company_id)
    return await get_company_by_id(session, company_id)


@timed_repository
async def count_users_for_company(session: AsyncSession, company_id: UUID) -> int:
    """Return the number of users linked to this company."""
    stmt = sa.select(sa.func.count(User.id)).where(
        User.company_id == company_id,
        User.is_active.is_(True),
    )
    return int((await session.execute(stmt)).scalar() or 0)


@timed_repository
async def company_application_metrics(
    session: AsyncSession, company_id: UUID
) -> dict[str, Any]:
    """Per-company application metrics (total / submitted / approved / sum)."""
    total_expr = sa.func.count(LeasingApplication.id)
    submitted_expr = sa.func.count(
        sa.case(
            (LeasingApplication.status == "active", LeasingApplication.id),
            else_=None,
        )
    )
    approved_expr = sa.func.count(
        sa.case(
            (LeasingApplication.status == "active", LeasingApplication.id),
            else_=None,
        )
    )
    total_amount_expr = sa.func.coalesce(
        sa.func.sum(LeasingApplication.total_amount), 0
    )
    stmt = sa.select(
        total_expr.label("total"),
        submitted_expr.label("submitted"),
        approved_expr.label("approved"),
        total_amount_expr.label("total_amount"),
    ).where(LeasingApplication.company_id == company_id)
    row = (await session.execute(stmt)).mappings().first()
    if row is None:
        return {
            "total_applications": 0,
            "submitted_applications": 0,
            "approved_applications": 0,
            "total_application_amount": 0,
        }
    return {
        "total_applications": int(row["total"] or 0),
        "submitted_applications": int(row["submitted"] or 0),
        "approved_applications": int(row["approved"] or 0),
        "total_application_amount": float(row["total_amount"] or 0),
    }


@timed_repository
async def count_company_vehicles_via_dealers(
    session: AsyncSession, company_id: UUID
) -> int:
    """Count vehicles whose dealer belongs to this company (dealer/distributor).

    Vehicles are owned by users (``vehicles.dealer_id``); company-level
    inventory is therefore the union of vehicles owned by any user whose
    ``users.company_id`` matches.
    """
    stmt = (
        sa.select(sa.func.count(SpecialEquipmentProduct.id))
        .where(SpecialEquipmentProduct.seller_company_id == company_id)
    )
    return int((await session.execute(stmt)).scalar() or 0)


@timed_repository
async def company_has_inn(session: AsyncSession, company_id: UUID) -> bool:
    stmt = sa.select(Company.inn).where(Company.id == company_id)
    inn = (await session.execute(stmt)).scalar_one_or_none()
    return bool(inn)


@timed_repository
async def is_user_linked_to_company(
    session: AsyncSession, user_id: UUID, company_id: UUID
) -> bool:
    """True iff the user is the primary owner or linked via user_companies."""
    primary = await get_user_company_id(session, user_id)
    if primary is not None and primary == company_id:
        return True
    linked = await list_user_company_ids(session, user_id)
    return company_id in set(linked)


@timed_repository
async def find_company_id_by_inn(session: AsyncSession, inn: str) -> UUID | None:
    """Return the company id matching ``inn`` or None."""
    stmt = sa.select(Company.id).where(Company.inn == inn)
    value = (await session.execute(stmt)).scalar_one_or_none()
    return value if value is not None else None


@timed_repository
async def attach_user_to_company(
    session: AsyncSession, user_id: UUID, company_id: UUID
) -> bool:
    """Update ``users.company_id`` to the given company id."""
    now = datetime.now(UTC)
    result = await session.execute(
        sa.update(User)
        .where(User.id == user_id)
        .values(company_id=company_id, updated_at=now)
    )
    await session.flush()
    return int(cast("sa.engine.CursorResult", result).rowcount or 0) > 0
