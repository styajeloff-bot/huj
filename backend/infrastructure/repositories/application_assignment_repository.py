"""Persistence for distributor/dealer and application employee assignments.

The repository exposes dict-only read models and scalar write results.  It
keeps the assignment use cases out of the much larger generic application
repository while sharing the same transaction/session.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from infrastructure.models.applications import (
    ApplicationVehicle,
    LeasingApplication,
)
from infrastructure.models.companies import Company
from infrastructure.models.special_equipment import SpecialEquipmentProduct
from infrastructure.models.support import DealerGroup, DealerGroupMember
from infrastructure.models.users import User, UserCompany
from infrastructure.models.vehicles import Warehouse
from infrastructure.repository_timing import timed_repository


def _active_warehouse_condition() -> Any:
    return sa.or_(Warehouse.status.is_(None), Warehouse.status == "active")


@timed_repository
async def application_has_company_warehouse_vehicle(
    session: AsyncSession,
    *,
    application_id: UUID,
    company_id: UUID,
) -> bool:
    """Return whether the application contains a unit on this company's stock."""
    stmt = (
        sa.select(
            sa.exists()
            .select_from(ApplicationVehicle)
            .join(SpecialEquipmentProduct, SpecialEquipmentProduct.id == ApplicationVehicle.product_id)
            .join(Warehouse, Warehouse.id == SpecialEquipmentProduct.warehouse_id)
            .where(
                ApplicationVehicle.application_id == application_id,
                Warehouse.company_id == company_id,
            )
        )
    )
    return bool((await session.execute(stmt)).scalar())


@timed_repository
async def list_assignable_dealer_groups(
    session: AsyncSession,
    *,
    distributor_company_id: UUID,
    brand: str | None = None,
) -> list[dict[str, Any]]:
    """Load groups, dealers and warehouse brands with one flat SQL query."""
    stmt = (
        sa.select(
            DealerGroup.id.label("group_id"),
            DealerGroup.name.label("group_name"),
            Company.id.label("dealer_id"),
            Company.name.label("dealer_name"),
            Company.inn.label("dealer_inn"),
            Warehouse.brand.label("warehouse_brand"),
        )
        .select_from(DealerGroup)
        .join(
            DealerGroupMember,
            DealerGroupMember.dealer_group_id == DealerGroup.id,
        )
        .join(Company, Company.id == DealerGroupMember.dealer_company_id)
        .outerjoin(
            Warehouse,
            sa.and_(
                Warehouse.company_id == Company.id,
                _active_warehouse_condition(),
            ),
        )
        .where(
            DealerGroup.distributor_company_id == distributor_company_id,
            DealerGroup.is_active.is_(True),
            Company.company_type == "dealer",
            Company.is_active.is_(True),
        )
        .order_by(
            sa.func.coalesce(DealerGroup.name, "").asc(),
            DealerGroup.id.asc(),
            sa.func.coalesce(Company.name, "").asc(),
            Company.id.asc(),
            sa.func.lower(sa.func.coalesce(Warehouse.brand, "")).asc(),
        )
    )
    normalized_brand = (brand or "").strip()
    if normalized_brand:
        matching_brand_warehouse = aliased(
            Warehouse,
            name="matching_brand_warehouse",
        )
        matching_warehouse = (
            sa.select(matching_brand_warehouse.id)
            .where(
                matching_brand_warehouse.company_id == Company.id,
                sa.or_(
                    matching_brand_warehouse.status.is_(None),
                    matching_brand_warehouse.status == "active",
                ),
                sa.func.lower(sa.func.trim(matching_brand_warehouse.brand))
                == normalized_brand.casefold(),
            )
            .correlate(Company)
            .exists()
        )
        stmt = stmt.where(matching_warehouse)

    rows = (await session.execute(stmt)).all()
    groups: list[dict[str, Any]] = []
    groups_by_id: dict[UUID, dict[str, Any]] = {}
    dealers_by_group: dict[UUID, dict[UUID, dict[str, Any]]] = {}
    brands_by_dealer: dict[tuple[UUID, UUID], set[str]] = {}

    for row in rows:
        group = groups_by_id.get(row.group_id)
        if group is None:
            group = {
                "id": row.group_id,
                "name": row.group_name,
                "dealers": [],
            }
            groups_by_id[row.group_id] = group
            dealers_by_group[row.group_id] = {}
            groups.append(group)

        dealer = dealers_by_group[row.group_id].get(row.dealer_id)
        if dealer is None:
            dealer = {
                "id": row.dealer_id,
                "name": row.dealer_name,
                "inn": row.dealer_inn,
                "brands": [],
            }
            dealers_by_group[row.group_id][row.dealer_id] = dealer
            brands_by_dealer[(row.group_id, row.dealer_id)] = set()
            group["dealers"].append(dealer)

        clean_brand = (row.warehouse_brand or "").strip()
        if clean_brand:
            brands_by_dealer[(row.group_id, row.dealer_id)].add(clean_brand)

    for group in groups:
        for dealer in group["dealers"]:
            dealer["brands"] = sorted(
                brands_by_dealer[(group["id"], dealer["id"])],
                key=lambda value: (value.casefold(), value),
            )
    return groups


@timed_repository
async def get_dealer_assignment_candidate(
    session: AsyncSession,
    *,
    dealer_group_id: UUID,
    dealer_company_id: UUID,
) -> dict[str, Any] | None:
    """Return group ownership and selected company/member facts in one row."""
    is_member = (
        sa.select(DealerGroupMember.id)
        .where(
            DealerGroupMember.dealer_group_id == dealer_group_id,
            DealerGroupMember.dealer_company_id == dealer_company_id,
        )
        .exists()
    )
    stmt = (
        sa.select(
            DealerGroup.id.label("group_id"),
            DealerGroup.distributor_company_id,
            DealerGroup.is_active.label("group_is_active"),
            Company.id.label("dealer_id"),
            Company.name.label("dealer_name"),
            Company.inn.label("dealer_inn"),
            Company.company_type.label("dealer_company_type"),
            Company.is_active.label("dealer_is_active"),
            is_member.label("dealer_is_member"),
        )
        .select_from(DealerGroup)
        .outerjoin(Company, Company.id == dealer_company_id)
        .where(DealerGroup.id == dealer_group_id)
    )
    row = (await session.execute(stmt)).first()
    if row is None:
        return None
    return {
        "group_id": row.group_id,
        "distributor_company_id": row.distributor_company_id,
        "group_is_active": bool(row.group_is_active),
        "dealer_id": row.dealer_id,
        "dealer_name": row.dealer_name,
        "dealer_inn": row.dealer_inn,
        "dealer_company_type": row.dealer_company_type,
        "dealer_is_active": bool(row.dealer_is_active),
        "dealer_is_member": bool(row.dealer_is_member),
    }


@timed_repository
async def update_dealer_assignment(
    session: AsyncSession,
    *,
    application_id: UUID,
    dealer_group_id: UUID,
    dealer_company_id: UUID,
    assigned_by: UUID,
) -> bool:
    application = await session.get(LeasingApplication, application_id)
    if application is None:
        return False
    assigned_at = datetime.now(UTC)
    application.dealer_company_id = dealer_company_id
    application.assigned_dealer_group_id = dealer_group_id
    application.dealer_assigned_by = assigned_by
    application.dealer_assigned_at = assigned_at
    cast("Any", application).updated_at = assigned_at
    await session.flush()
    return True


@timed_repository
async def search_company_employees(
    session: AsyncSession,
    *,
    company_id: UUID,
    query: str | None,
    limit: int,
) -> list[dict[str, Any]]:
    membership_sub_role = sa.case(
        (
            UserCompany.user_id.is_not(None),
            sa.func.coalesce(UserCompany.sub_role, "employee"),
        ),
        (
            User.company_id == company_id,
            sa.literal("administrator"),
        ),
        else_=None,
    ).label("sub_role")
    stmt = (
        sa.select(
            User.id,
            User.name,
            User.phone,
            membership_sub_role,
        )
        .select_from(User)
        .outerjoin(
            UserCompany,
            sa.and_(
                UserCompany.user_id == User.id,
                UserCompany.company_id == company_id,
            ),
        )
        .where(
            sa.or_(
                User.company_id == company_id,
                UserCompany.company_id == company_id,
            ),
            User.is_active.is_(True),
            User.deleted_at.is_(None),
        )
        .order_by(
            sa.func.coalesce(User.name, "").asc(),
            User.id.asc(),
        )
        .limit(limit)
    )
    normalized_query = (query or "").strip()
    if normalized_query:
        pattern = f"%{normalized_query}%"
        stmt = stmt.where(
            sa.or_(
                User.name.ilike(pattern),
                User.phone.ilike(pattern),
                membership_sub_role.ilike(pattern),
            )
        )
    rows = (await session.execute(stmt)).all()
    return [
        {
            "id": row.id,
            "name": row.name,
            "phone": row.phone,
            "sub_role": row.sub_role,
        }
        for row in rows
    ]


@timed_repository
async def get_active_company_employee(
    session: AsyncSession,
    *,
    company_id: UUID,
    employee_id: UUID,
) -> dict[str, Any] | None:
    membership_sub_role = sa.case(
        (
            UserCompany.user_id.is_not(None),
            sa.func.coalesce(UserCompany.sub_role, "employee"),
        ),
        (
            User.company_id == company_id,
            sa.literal("administrator"),
        ),
        else_=None,
    ).label("sub_role")
    stmt = (
        sa.select(
            User.id,
            User.name,
            User.phone,
            membership_sub_role,
        )
        .select_from(User)
        .outerjoin(
            UserCompany,
            sa.and_(
                UserCompany.user_id == User.id,
                UserCompany.company_id == company_id,
            ),
        )
        .where(
            User.id == employee_id,
            sa.or_(
                User.company_id == company_id,
                UserCompany.company_id == company_id,
            ),
            User.is_active.is_(True),
            User.deleted_at.is_(None),
        )
    )
    row = (await session.execute(stmt)).first()
    if row is None:
        return None
    return {
        "id": row.id,
        "name": row.name,
        "phone": row.phone,
        "sub_role": row.sub_role,
    }


@timed_repository
async def update_employee_assignment(
    session: AsyncSession,
    *,
    application_id: UUID,
    employee_fields: dict[str, UUID | None],
    assigned_by: UUID,
) -> bool:
    application = await session.get(LeasingApplication, application_id)
    if application is None:
        return False
    assigned_at = datetime.now(UTC)
    for key, value in employee_fields.items():
        setattr(application, key, value)
    application.employees_assigned_by = assigned_by
    application.employees_assigned_at = assigned_at
    cast("Any", application).updated_at = assigned_at
    await session.flush()
    return True


@timed_repository
async def get_assignment_details(
    session: AsyncSession,
    *,
    application_id: UUID,
    actor_company_id: UUID | None,
) -> dict[str, Any]:
    """Return display resources for all assignment/audit foreign keys."""
    dealer = aliased(Company, name="assigned_dealer_company")
    primary = aliased(User, name="primary_employee")
    additional = aliased(User, name="additional_employee")
    dealer_actor = aliased(User, name="dealer_assignment_actor")
    employees_actor = aliased(User, name="employees_assignment_actor")
    primary_membership = aliased(UserCompany, name="primary_employee_membership")
    additional_membership = aliased(
        UserCompany,
        name="additional_employee_membership",
    )
    membership_company_condition: Any = (
        actor_company_id
        if actor_company_id is not None
        else sa.null()
    )
    primary_sub_role = sa.case(
        (
            primary_membership.user_id.is_not(None),
            sa.func.coalesce(primary_membership.sub_role, "employee"),
        ),
        (
            primary.company_id == membership_company_condition,
            sa.literal("administrator"),
        ),
        else_=None,
    )
    additional_sub_role = sa.case(
        (
            additional_membership.user_id.is_not(None),
            sa.func.coalesce(additional_membership.sub_role, "employee"),
        ),
        (
            additional.company_id == membership_company_condition,
            sa.literal("administrator"),
        ),
        else_=None,
    )

    stmt = (
        sa.select(
            dealer.id.label("dealer_id"),
            dealer.name.label("dealer_name"),
            dealer.inn.label("dealer_inn"),
            primary.id.label("primary_id"),
            primary.name.label("primary_name"),
            primary.phone.label("primary_phone"),
            primary_sub_role.label("primary_sub_role"),
            additional.id.label("additional_id"),
            additional.name.label("additional_name"),
            additional.phone.label("additional_phone"),
            additional_sub_role.label("additional_sub_role"),
            dealer_actor.id.label("dealer_actor_id"),
            dealer_actor.name.label("dealer_actor_name"),
            employees_actor.id.label("employees_actor_id"),
            employees_actor.name.label("employees_actor_name"),
        )
        .select_from(LeasingApplication)
        .outerjoin(dealer, dealer.id == LeasingApplication.dealer_company_id)
        .outerjoin(primary, primary.id == LeasingApplication.primary_employee_id)
        .outerjoin(
            primary_membership,
            sa.and_(
                primary_membership.user_id == primary.id,
                primary_membership.company_id == membership_company_condition,
            ),
        )
        .outerjoin(
            additional,
            additional.id == LeasingApplication.additional_employee_id,
        )
        .outerjoin(
            additional_membership,
            sa.and_(
                additional_membership.user_id == additional.id,
                additional_membership.company_id == membership_company_condition,
            ),
        )
        .outerjoin(
            dealer_actor,
            dealer_actor.id == LeasingApplication.dealer_assigned_by,
        )
        .outerjoin(
            employees_actor,
            employees_actor.id == LeasingApplication.employees_assigned_by,
        )
        .where(LeasingApplication.id == application_id)
    )
    row = (await session.execute(stmt)).first()
    if row is None:
        return {
            "assigned_dealer": None,
            "primary_employee": None,
            "additional_employee": None,
            "dealer_assigned_by": None,
            "employees_assigned_by": None,
        }

    return {
        "assigned_dealer": (
            {
                "id": row.dealer_id,
                "name": row.dealer_name,
                "inn": row.dealer_inn,
            }
            if row.dealer_id is not None
            else None
        ),
        "primary_employee": (
            {
                "id": row.primary_id,
                "name": row.primary_name,
                "phone": row.primary_phone,
                "sub_role": row.primary_sub_role,
            }
            if row.primary_id is not None
            else None
        ),
        "additional_employee": (
            {
                "id": row.additional_id,
                "name": row.additional_name,
                "phone": row.additional_phone,
                "sub_role": row.additional_sub_role,
            }
            if row.additional_id is not None
            else None
        ),
        "dealer_assigned_by": (
            {
                "id": row.dealer_actor_id,
                "name": row.dealer_actor_name,
            }
            if row.dealer_actor_id is not None
            else None
        ),
        "employees_assigned_by": (
            {
                "id": row.employees_actor_id,
                "name": row.employees_actor_name,
            }
            if row.employees_actor_id is not None
            else None
        ),
    }


__all__ = [
    "application_has_company_warehouse_vehicle",
    "get_active_company_employee",
    "get_assignment_details",
    "get_dealer_assignment_candidate",
    "list_assignable_dealer_groups",
    "search_company_employees",
    "update_dealer_assignment",
    "update_employee_assignment",
]
