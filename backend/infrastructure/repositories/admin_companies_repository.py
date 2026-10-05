"""Admin-side companies repository — create + directory listings.

Owns ORM access for ``companies``, ``leasing_companies`` and ``distributors``
as used from the admin surface: creation with optional DaData-enrichment
payload plus unfiltered directory listings (LC list, distributor list).
"""

from __future__ import annotations

import uuid
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.models.companies import Company, Distributor, LeasingCompany
from infrastructure.repositories.company_address_guard import (
    ensure_company_addresses_are_not_blank,
)
from infrastructure.repository_timing import timed_repository


@timed_repository
async def inn_exists(session: AsyncSession, inn: str) -> bool:
    stmt = select(Company.id).where(Company.inn == inn)
    return (await session.execute(stmt)).first() is not None


@timed_repository
async def create_company(
    session: AsyncSession,
    *,
    name: str,
    inn: str,
    kpp: str | None,
    ogrn: str | None,
    company_type: str,
    legal_address: str | None,
    phone: str | None,
    email: str | None,
    full_name: str | None,
    short_name: str | None,
    legal_address_details: dict[str, Any] | None,
    founders: list[dict[str, Any]] | dict[str, Any] | None,
    additional_okved_list: list[dict[str, Any]] | dict[str, Any] | None,
    main_okved_code: str | None,
    main_okved_description: str | None,
    director_full_name: str | None,
    director_position: str | None,
    enrichment_status: str | None,
    company_id: UUID | None = None,
    city: str | None = None,
    region: str | None = None,
    actual_address: str | None = None,
) -> uuid.UUID:
    ensure_company_addresses_are_not_blank(
        {
            "legal_address": legal_address,
            "actual_address": actual_address,
        }
    )
    row = Company(
        id=company_id or uuid.uuid4(),
        name=name,
        inn=inn,
        kpp=kpp,
        ogrn=ogrn,
        company_type=company_type,
        legal_address=legal_address,
        actual_address=actual_address,
        city=city,
        region=region,
        phone=phone,
        email=email,
        is_active=True,
        full_name=full_name,
        short_name=short_name,
        legal_address_details=legal_address_details,
        founders=founders,
        additional_okved_list=additional_okved_list,
        main_okved_code=main_okved_code,
        main_okved_description=main_okved_description,
        director_full_name=director_full_name,
        director_position=director_position,
        enrichment_status=enrichment_status,
    )
    session.add(row)
    await session.flush()
    return row.id


@timed_repository
async def create_leasing_company(session: AsyncSession, *, company_id: UUID) -> UUID:
    row = LeasingCompany(company_id=company_id, is_active=True)
    session.add(row)
    await session.flush()
    return row.id


@timed_repository
async def create_distributor(session: AsyncSession, *, company_id: UUID) -> UUID:
    row = Distributor(company_id=company_id, is_active=True)
    session.add(row)
    await session.flush()
    return row.id


@timed_repository
async def get_by_id(session: AsyncSession, company_id: UUID) -> dict[str, Any] | None:
    row = await session.get(Company, company_id)
    if row is None:
        return None
    return {
        "id": row.id,
        "name": row.name,
        "inn": row.inn,
        "kpp": row.kpp,
        "ogrn": row.ogrn,
        "company_type": row.company_type,
        "legal_address": row.legal_address,
        "actual_address": row.actual_address,
        "city": row.city,
        "region": row.region,
        "address": row.address,
        "contact_info": row.contact_info,
        "phone": row.phone,
        "email": row.email,
        "website": row.website,
        "is_active": row.is_active,
        "full_name": row.full_name,
        "short_name": row.short_name,
        "okpo": row.okpo,
        "okato": row.okato,
        "legal_form": row.legal_form,
        "registration_date": row.registration_date,
        "employees_count": row.employees_count,
        "main_okved_code": row.main_okved_code,
        "main_okved_description": row.main_okved_description,
        "director_full_name": row.director_full_name,
        "bank_bik": row.bank_bik,
        "bank_name": row.bank_name,
        "authorized_capital": row.authorized_capital,
        "net_profit": row.net_profit,
        "reporting_year": row.reporting_year,
        "tax_system": row.tax_system,
        "enrichment_status": row.enrichment_status,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


@timed_repository
async def list_leasing_companies_all(
    session: AsyncSession,
) -> list[dict[str, Any]]:
    """Full directory of leasing companies (with company display fields).

    Used by the admin UI for selection in application assignment.
    """
    stmt = (
        select(
            LeasingCompany.id,
            Company.id.label("company_id"),
            Company.name,
            Company.inn,
            Company.phone,
            Company.email,
            Company.is_active.label("company_is_active"),
            LeasingCompany.is_active.label("lc_is_active"),
            LeasingCompany.average_down_payment_percent,
            LeasingCompany.average_lease_term_months,
        )
        .join(Company, Company.id == LeasingCompany.company_id, isouter=True)
        .where(Company.company_type == "leasing_company")
        .order_by(func.coalesce(Company.name, "").asc())
    )
    rows = (await session.execute(stmt)).all()
    return [
        {
            "id": row.id,
            "company_id": row.company_id,
            "name": row.name,
            "inn": row.inn,
            "phone": row.phone,
            "email": row.email,
            "is_active": bool(
                (row.lc_is_active is None or row.lc_is_active)
                and (row.company_is_active is None or row.company_is_active)
            ),
            "average_down_payment_percent": row.average_down_payment_percent,
            "average_lease_term_months": row.average_lease_term_months,
        }
        for row in rows
    ]


@timed_repository
async def list_distributors_all(
    session: AsyncSession,
) -> list[dict[str, Any]]:
    """Full directory of distributor companies.

    Admin selectors are company-based: distributor companies may exist without
    a legacy ``distributors`` extension row after bulk imports.
    """
    stmt = (
        select(
            Company.id,
            Company.name,
            Company.inn,
            Company.phone,
            Company.email,
            Distributor.can_manage_dealer_groups,
        )
        .join(Distributor, Distributor.company_id == Company.id, isouter=True)
        .where(
            Company.is_active.is_(True),
            Company.company_type == "distributor",
        )
        .order_by(func.coalesce(Company.name, "").asc())
    )
    rows = (await session.execute(stmt)).all()
    return [
        {
            "id": row.id,
            "company_id": row.id,
            "name": row.name,
            "inn": row.inn,
            "phone": row.phone,
            "email": row.email,
            "is_active": True,
            "can_manage_dealer_groups": bool(row.can_manage_dealer_groups),
        }
        for row in rows
    ]


@timed_repository
async def count_active_companies_by_type(
    session: AsyncSession,
) -> dict[str, int]:
    stmt = (
        select(Company.company_type, func.count(Company.id))
        .where(Company.is_active.is_(True))
        .group_by(Company.company_type)
    )
    rows = (await session.execute(stmt)).all()
    return {str(r[0] or "unknown"): int(r[1] or 0) for r in rows}


@timed_repository
async def count_active_companies_total(session: AsyncSession) -> int:
    stmt = select(func.count(Company.id)).where(Company.is_active.is_(True))
    return int((await session.execute(stmt)).scalar() or 0)
