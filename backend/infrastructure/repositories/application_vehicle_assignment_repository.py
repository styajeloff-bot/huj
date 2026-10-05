"""Persistence for dealer and employee assignments on application vehicles."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from infrastructure.models.applications import (
    ApplicationVehicle,
    ApplicationVehicleDealerDistribution,
)
from infrastructure.models.companies import Company, DistributorDealerLink
from infrastructure.models.special_equipment import SpecialEquipmentProduct
from infrastructure.models.support import DealerGroup, DealerGroupMember
from infrastructure.models.users import User, UserCompany
from infrastructure.models.vehicles import Warehouse
from infrastructure.repository_timing import timed_repository


def _assignment_dict(row: Any) -> dict[str, Any]:
    return {
        "id": row.id,
        "application_id": row.application_id,
        "vehicle_id": row.vehicle_id,
        "dealer_company_id": row.dealer_company_id,
        "dealer_assigned_by_id": row.dealer_assigned_by,
        "dealer_assigned_at": row.dealer_assigned_at,
        "primary_employee_id": row.primary_employee_id,
        "additional_employee_id": row.additional_employee_id,
        "employees_assigned_by_id": row.employees_assigned_by,
        "employees_assigned_at": row.employees_assigned_at,
    }


def _effective_assigned_dealer_id(actor_dealer_company_id: UUID | None = None) -> Any:
    """One full recipient is the effective assignee; a dealer sees its own share."""
    distribution = ApplicationVehicleDealerDistribution
    full_dealer = (
        sa.select(distribution.dealer_company_id)
        .where(distribution.application_vehicle_id == ApplicationVehicle.id)
        .group_by(distribution.dealer_company_id)
        .having(sa.func.sum(distribution.quantity) == ApplicationVehicle.quantity)
        .correlate(ApplicationVehicle)
        .scalar_subquery()
    )
    legacy_dealer = (
        sa.select(Company.id)
        .where(Company.id == ApplicationVehicle.dealer_company_id, Company.company_type == "dealer")
        .correlate(ApplicationVehicle)
        .scalar_subquery()
    )
    effective_dealer = sa.func.coalesce(full_dealer, legacy_dealer)
    if actor_dealer_company_id is None:
        return effective_dealer
    owns_share = sa.exists().where(
        distribution.application_vehicle_id == ApplicationVehicle.id,
        distribution.dealer_company_id == actor_dealer_company_id,
    ).correlate(ApplicationVehicle)
    return sa.case((owns_share, actor_dealer_company_id), else_=effective_dealer)


@timed_repository
async def get_assignment(
    session: AsyncSession,
    *,
    application_id: UUID,
    application_vehicle_id: UUID,
) -> dict[str, Any] | None:
    stmt = sa.select(ApplicationVehicle, _effective_assigned_dealer_id().label("effective_dealer_id")).where(
        ApplicationVehicle.id == application_vehicle_id,
        ApplicationVehicle.application_id == application_id,
    )
    row = (await session.execute(stmt)).one_or_none()
    if row is None:
        return None
    result = _assignment_dict(row.ApplicationVehicle)
    result["dealer_company_id"] = row.effective_dealer_id
    return result


@timed_repository
async def application_vehicle_is_in_company_scope(
    session: AsyncSession,
    *,
    application_id: UUID,
    application_vehicle_id: UUID,
    company_ids: list[UUID],
) -> bool:
    """Check inventory ownership against a distributor's complete scope."""

    if not company_ids:
        return False
    inventory_owner = sa.func.coalesce(
        Warehouse.company_id,
        Warehouse.dealer_id,
        SpecialEquipmentProduct.seller_company_id,
    )
    stmt = sa.select(
        sa.exists()
        .select_from(ApplicationVehicle)
        .join(SpecialEquipmentProduct, SpecialEquipmentProduct.id == ApplicationVehicle.product_id)
        .outerjoin(Warehouse, Warehouse.id == SpecialEquipmentProduct.warehouse_id)
        .where(
            ApplicationVehicle.id == application_vehicle_id,
            ApplicationVehicle.application_id == application_id,
            inventory_owner.in_(company_ids),
        )
    )
    return bool((await session.execute(stmt)).scalar())


@timed_repository
async def get_linked_dealer_candidate(
    session: AsyncSession,
    *,
    distributor_company_id: UUID,
    dealer_company_id: UUID,
) -> dict[str, Any] | None:
    direct_link = sa.exists().where(
        DistributorDealerLink.distributor_company_id == distributor_company_id,
        DistributorDealerLink.dealer_company_id == Company.id,
    )
    active_group_membership = (
        sa.exists()
        .where(DealerGroupMember.dealer_company_id == Company.id)
        .where(DealerGroupMember.dealer_group_id == DealerGroup.id)
        .where(DealerGroup.distributor_company_id == distributor_company_id)
        .where(DealerGroup.is_active.is_(True))
    )
    stmt = (
        sa.select(
            Company.id,
            Company.name,
            Company.inn,
            Company.company_type,
            Company.is_active,
        )
        .select_from(Company)
        .where(
            Company.id == dealer_company_id,
            sa.or_(direct_link, active_group_membership),
        )
    )
    row = (await session.execute(stmt)).first()
    if row is None:
        return None
    return {
        "id": row.id,
        "name": row.name,
        "inn": row.inn,
        "company_type": row.company_type,
        "is_active": bool(row.is_active),
    }


@timed_repository
async def update_dealer_assignment(
    session: AsyncSession,
    *,
    application_id: UUID,
    application_vehicle_id: UUID,
    dealer_company_id: UUID,
    assigned_by: UUID,
) -> bool:
    row = await session.get(ApplicationVehicle, application_vehicle_id)
    if row is None or row.application_id != application_id:
        return False
    changed = row.dealer_company_id != dealer_company_id
    now = datetime.now(UTC)
    row.dealer_company_id = dealer_company_id
    row.dealer_assigned_by = assigned_by
    row.dealer_assigned_at = now
    if changed:
        row.primary_employee_id = None
        row.additional_employee_id = None
        row.employees_assigned_by = assigned_by
        row.employees_assigned_at = now
    await session.flush()
    return True


@timed_repository
async def update_employee_assignment(
    session: AsyncSession,
    *,
    application_id: UUID,
    application_vehicle_id: UUID,
    employee_fields: dict[str, UUID | None],
    assigned_by: UUID,
) -> bool:
    row = await session.get(ApplicationVehicle, application_vehicle_id)
    if row is None or row.application_id != application_id:
        return False
    for key, value in employee_fields.items():
        setattr(row, key, value)
    row.employees_assigned_by = assigned_by
    row.employees_assigned_at = datetime.now(UTC)
    await session.flush()
    return True


@timed_repository
async def list_assignment_details(
    session: AsyncSession,
    application_vehicle_ids: list[UUID],
    *, actor_dealer_company_id: UUID | None = None,
) -> dict[UUID, dict[str, Any]]:
    if not application_vehicle_ids:
        return {}
    dealer = aliased(Company, name="vehicle_assigned_dealer")
    primary = aliased(User, name="vehicle_primary_employee")
    additional = aliased(User, name="vehicle_additional_employee")
    dealer_actor = aliased(User, name="vehicle_dealer_assignment_actor")
    employees_actor = aliased(User, name="vehicle_employees_assignment_actor")
    primary_membership = aliased(UserCompany, name="vehicle_primary_membership")
    additional_membership = aliased(UserCompany, name="vehicle_additional_membership")
    effective_dealer_id = _effective_assigned_dealer_id(actor_dealer_company_id)
    primary_sub_role = sa.case(
        (
            primary_membership.user_id.is_not(None),
            sa.func.coalesce(primary_membership.sub_role, "employee"),
        ),
        (
            primary.company_id == effective_dealer_id,
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
            additional.company_id == effective_dealer_id,
            sa.literal("administrator"),
        ),
        else_=None,
    )
    stmt = (
        sa.select(
            ApplicationVehicle.id.label("application_vehicle_id"),
            effective_dealer_id.label("dealer_company_id"),
            ApplicationVehicle.dealer_assigned_by.label("dealer_assigned_by_id"),
            ApplicationVehicle.dealer_assigned_at,
            ApplicationVehicle.primary_employee_id,
            ApplicationVehicle.additional_employee_id,
            ApplicationVehicle.employees_assigned_by.label("employees_assigned_by_id"),
            ApplicationVehicle.employees_assigned_at,
            dealer.name.label("dealer_name"),
            dealer.inn.label("dealer_inn"),
            primary.name.label("primary_name"),
            primary.phone.label("primary_phone"),
            primary_sub_role.label("primary_sub_role"),
            additional.name.label("additional_name"),
            additional.phone.label("additional_phone"),
            additional_sub_role.label("additional_sub_role"),
            dealer_actor.name.label("dealer_actor_name"),
            employees_actor.name.label("employees_actor_name"),
        )
        .select_from(ApplicationVehicle)
        .outerjoin(dealer, dealer.id == effective_dealer_id)
        .outerjoin(primary, primary.id == ApplicationVehicle.primary_employee_id)
        .outerjoin(
            primary_membership,
            sa.and_(
                primary_membership.user_id == primary.id,
                primary_membership.company_id == effective_dealer_id,
            ),
        )
        .outerjoin(
            additional, additional.id == ApplicationVehicle.additional_employee_id
        )
        .outerjoin(
            additional_membership,
            sa.and_(
                additional_membership.user_id == additional.id,
                additional_membership.company_id
                == effective_dealer_id,
            ),
        )
        .outerjoin(
            dealer_actor, dealer_actor.id == ApplicationVehicle.dealer_assigned_by
        )
        .outerjoin(
            employees_actor,
            employees_actor.id == ApplicationVehicle.employees_assigned_by,
        )
        .where(ApplicationVehicle.id.in_(application_vehicle_ids))
    )
    rows = (await session.execute(stmt)).all()
    return {
        row.application_vehicle_id: {
            "dealer_company_id": row.dealer_company_id,
            "assigned_dealer": (
                {
                    "id": row.dealer_company_id,
                    "name": row.dealer_name,
                    "inn": row.dealer_inn,
                }
                if row.dealer_company_id is not None
                else None
            ),
            "dealer_assigned_by_id": row.dealer_assigned_by_id,
            "dealer_assigned_by": (
                {"id": row.dealer_assigned_by_id, "name": row.dealer_actor_name}
                if row.dealer_assigned_by_id is not None
                else None
            ),
            "dealer_assigned_at": row.dealer_assigned_at,
            "primary_employee_id": row.primary_employee_id,
            "primary_employee": (
                {
                    "id": row.primary_employee_id,
                    "name": row.primary_name,
                    "phone": row.primary_phone,
                    "sub_role": row.primary_sub_role,
                }
                if row.primary_employee_id is not None
                else None
            ),
            "additional_employee_id": row.additional_employee_id,
            "additional_employee": (
                {
                    "id": row.additional_employee_id,
                    "name": row.additional_name,
                    "phone": row.additional_phone,
                    "sub_role": row.additional_sub_role,
                }
                if row.additional_employee_id is not None
                else None
            ),
            "employees_assigned_by_id": row.employees_assigned_by_id,
            "employees_assigned_by": (
                {"id": row.employees_assigned_by_id, "name": row.employees_actor_name}
                if row.employees_assigned_by_id is not None
                else None
            ),
            "employees_assigned_at": row.employees_assigned_at,
        }
        for row in rows
    }


async def get_assignment_details(
    session: AsyncSession,
    *,
    application_vehicle_id: UUID,
) -> dict[str, Any]:
    details = await list_assignment_details(session, [application_vehicle_id])
    return details.get(application_vehicle_id, {})


__all__ = [
    "application_vehicle_is_in_company_scope",
    "get_assignment",
    "get_assignment_details",
    "get_linked_dealer_candidate",
    "list_assignment_details",
    "update_dealer_assignment",
    "update_employee_assignment",
]
