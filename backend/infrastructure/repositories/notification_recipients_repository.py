"""Participant/membership projections; authorization stays in shared use cases."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import String, and_, cast, exists, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.models.applications import (
    LeasingApplication,
    LeasingCompanyApplication,
)
from infrastructure.models.companies import Company, LeasingCompany, LeasingCompanyUser
from infrastructure.models.storefronts import Storefront
from infrastructure.models.users import User, UserCompany
from infrastructure.repositories import application_repository as app_repo


async def leasing_context(
    session: AsyncSession, application_id: UUID
) -> dict[str, Any] | None:
    application = await app_repo.get_by_id(session, application_id)
    if application is None:
        return None
    dealer_ids = set(
        (
            await session.scalars(
                select(Company.id).where(
                    Company.company_type == "dealer",
                    Company.is_active.is_(True),
                    or_(
                        Company.id == application.get("dealer_company_id"),
                        app_repo.dealer_child_ownership_clause(
                            application_id, Company.id
                        ),
                    ),
                )
            )
        ).all()
    )
    lc_rows = (
        await session.execute(
            select(LeasingCompany.id, LeasingCompany.company_id)
            .join(
                LeasingCompanyApplication,
                LeasingCompanyApplication.leasing_company_id == LeasingCompany.id,
            )
            .where(
                LeasingCompanyApplication.application_id == application_id,
                LeasingCompany.is_active.is_(True),
            )
        )
    ).all()
    # Object scope (warehouse / linked dealer / group) is checked individually.
    distributor_ids = set(
        (
            await session.scalars(
                select(Company.id).where(
                    Company.company_type == "distributor",
                    Company.is_active.is_(True),
                )
            )
        ).all()
    )
    storefront_slug = await session.scalar(
        select(Storefront.slug)
        .join(LeasingApplication, LeasingApplication.storefront_id == Storefront.id)
        .where(LeasingApplication.id == application_id)
    )
    return {
        "application": application,
        "dealer_company_ids": dealer_ids,
        "lc_company_ids": {row.id: row.company_id for row in lc_rows if row.company_id},
        "distributor_company_ids": distributor_ids,
        "storefront_slug": storefront_slug,
    }


async def candidate_contexts(
    session: AsyncSession,
    *,
    company_ids: set[UUID],
    include_employees: bool = False,
    user_id: UUID | None = None,
    readable_only: bool = True,
) -> list[dict[str, Any]]:
    """Fresh memberships; notification candidates require read access by default.

    Ordinary HTTP contexts may request the unfiltered permission projection so
    their operation-specific guard can independently evaluate create permission.
    """
    linked_lc = exists(
        select(LeasingCompanyUser.id)
        .join(
            LeasingCompany,
            LeasingCompany.id == LeasingCompanyUser.leasing_company_id,
        )
        .where(
            LeasingCompanyUser.user_id == User.id,
            LeasingCompany.company_id == Company.id,
            LeasingCompany.is_active.is_(True),
        )
    )
    stmt = (
        select(
            User.id,
            User.role,
            User.email,
            Company.id.label("company_id"),
            UserCompany.user_id.label("membership_id"),
            UserCompany.can_view_applications,
            UserCompany.can_create_applications,
            UserCompany.sub_role,
        )
        .select_from(User)
        .join(
            Company,
            Company.id.in_(company_ids),
        )
        .outerjoin(
            UserCompany,
            and_(UserCompany.user_id == User.id, UserCompany.company_id == Company.id),
        )
        .where(
            User.is_active.is_(True),
            User.deleted_at.is_(None),
            Company.is_active.is_(True),
            or_(
                UserCompany.user_id.is_not(None),
                User.company_id == Company.id,
                and_(User.role == "leasing_company", linked_lc),
            ),
            or_(
                cast(User.role, String) == cast(Company.company_type, String),
                User.role == "client",
            ),
        )
    )
    if user_id is not None:
        stmt = stmt.where(User.id == user_id)
    contexts = [
        {
            "user_id": row.id,
            "role": row.role,
            "email": row.email,
            "company_id": row.company_id,
            "can_view_applications": bool(row.can_view_applications) if row.membership_id else True,
            "can_create_applications": bool(row.can_create_applications) if row.membership_id else True,
            "sub_role": (row.sub_role or "employee") if row.membership_id else "administrator",
        }
        for row in (await session.execute(stmt)).all()
        if not readable_only or row.membership_id is None or row.can_view_applications
    ]
    if include_employees:
        employees = select(User).where(
            User.role == "carcraft_employee",
            User.is_active.is_(True),
            User.deleted_at.is_(None),
        )
        if user_id is not None:
            employees = employees.where(User.id == user_id)
        contexts.extend(
            {
                "user_id": row.id,
                "role": row.role,
                "email": row.email,
                "company_id": None,
            }
            for row in (await session.scalars(employees)).all()
        )
    return contexts


async def get_user(session: AsyncSession, user_id: UUID) -> dict[str, Any] | None:
    row = (await session.execute(select(
        User.id, User.email, User.role, User.name, User.is_active, User.deleted_at,
    ).where(User.id == user_id))).one_or_none()
    if row is None:
        return None
    return {
        "id": row.id,
        "email": row.email,
        "role": row.role,
        "name": row.name,
        "is_active": row.is_active is True and row.deleted_at is None,
    }


async def lc_ids_for_company(session: AsyncSession, company_id: UUID) -> list[UUID]:
    return list(
        (
            await session.scalars(
                select(LeasingCompany.id).where(
                    LeasingCompany.company_id == company_id,
                    LeasingCompany.is_active.is_(True),
                )
            )
        ).all()
    )


async def distributor_company_ids(session: AsyncSession) -> set[UUID]:
    return set(
        (
            await session.scalars(
                select(Company.id).where(
                    Company.company_type == "distributor",
                    Company.is_active.is_(True),
                )
            )
        ).all()
    )
