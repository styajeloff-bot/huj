"""Repository for user company personal access rules, section access and employee permissions."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.models.companies import Company, DistributorDealerLink
from infrastructure.models.special_equipment import SpecialEquipmentMark
from infrastructure.models.user_company_access import (
    UserCompanyAccessRule,
    UserCompanyEmployeePermission,
    UserCompanySectionAccess,
)
from infrastructure.models.users import User, UserCompany
from infrastructure.models.vehicles import Warehouse

ALL_SECTION_CODES: tuple[str, ...] = (
    "applications",
    "warehouses",
    "vehicle_exchange",
    "employees",
    "catalog_management",
    "analytics",
    "monetization_income",
    "monetization_expense",
    "incentive_programs",
)


@dataclass
class PersonalAccessRules:
    has_rules: bool = False
    application_creator_mode: str | None = None  # 'all', 'selected', 'except_selected', 'none'
    application_creator_ids: set[UUID] = field(default_factory=set)
    dealer_mode: str | None = None  # 'all', 'selected', 'none'
    dealer_ids: set[UUID] = field(default_factory=set)
    warehouse_mode: str | None = None  # 'all', 'selected', 'except_selected', 'none'
    warehouse_ids: set[UUID] = field(default_factory=set)
    dealer_warehouse_mode: str | None = None  # 'all', 'selected', 'except_selected', 'none'
    dealer_warehouse_ids: set[UUID] = field(default_factory=set)
    brand_mode: str | None = None  # 'all', 'selected', 'except_selected', 'none'
    brand_ids: set[UUID] = field(default_factory=set)


async def get_user_company(
    session: AsyncSession,
    user_id: UUID,
    company_id: UUID,
) -> UserCompany | None:
    """Retrieve active user_company link row."""
    stmt = select(UserCompany).where(
        UserCompany.user_id == user_id,
        UserCompany.company_id == company_id,
        UserCompany.is_active.is_(True),
    )
    return (await session.execute(stmt)).scalar_one_or_none()


get_user_company_by_user_and_company = get_user_company


async def get_user_company_access_rules(
    session: AsyncSession,
    user_company_id: UUID,
) -> list[UserCompanyAccessRule]:
    """Retrieve all active object-level access rules for a user_company link."""
    stmt = (
        select(UserCompanyAccessRule)
        .where(
            UserCompanyAccessRule.user_company_id == user_company_id,
            UserCompanyAccessRule.is_active.is_(True),
        )
        .order_by(UserCompanyAccessRule.access_object, UserCompanyAccessRule.created_at)
    )
    return list((await session.execute(stmt)).scalars().all())


async def get_user_company_section_access(
    session: AsyncSession,
    user_company_id: UUID,
) -> dict[str, bool]:
    """Retrieve section visibility map for a user_company link."""
    stmt = select(UserCompanySectionAccess).where(
        UserCompanySectionAccess.user_company_id == user_company_id,
    )
    rows = (await session.execute(stmt)).scalars().all()
    return {row.section_code: row.can_view for row in rows}


async def get_employee_permission(
    session: AsyncSession,
    user_company_id: UUID,
) -> UserCompanyEmployeePermission | None:
    """Retrieve employee management permission for a user_company link."""
    stmt = select(UserCompanyEmployeePermission).where(
        UserCompanyEmployeePermission.user_company_id == user_company_id,
    )
    return (await session.execute(stmt)).scalar_one_or_none()


def _parse_rule_uuid(object_id: str | None) -> UUID | None:
    if not object_id:
        return None
    try:
        return UUID(object_id)
    except (ValueError, TypeError):
        return None


def _apply_rule_to_personal_access(rule: UserCompanyAccessRule, target: PersonalAccessRules) -> None:
    obj = rule.access_object
    atype = rule.access_type
    parsed_id = _parse_rule_uuid(rule.object_id)

    if obj == "application_creator":
        target.application_creator_mode = atype
        if parsed_id:
            target.application_creator_ids.add(parsed_id)
    elif obj == "dealer":
        target.dealer_mode = atype
        if parsed_id:
            target.dealer_ids.add(parsed_id)
    elif obj == "warehouse":
        target.warehouse_mode = atype
        if parsed_id:
            target.warehouse_ids.add(parsed_id)
    elif obj == "dealer_warehouse":
        target.dealer_warehouse_mode = atype
        if parsed_id:
            target.dealer_warehouse_ids.add(parsed_id)
    elif obj == "brand":
        target.brand_mode = atype
        if parsed_id:
            target.brand_ids.add(parsed_id)


async def get_actor_personal_access_rules(
    session: AsyncSession,
    user_id: UUID,
    company_id: UUID | None,
) -> PersonalAccessRules:
    """Load and parse personal access rules for actor's active company.

    Returns PersonalAccessRules with has_rules=False if no company or no rules are set.
    """
    if company_id is None:
        return PersonalAccessRules(has_rules=False)

    uc = await get_user_company(session, user_id, company_id)
    if uc is None or uc.id is None:
        return PersonalAccessRules(has_rules=False)

    rules = await get_user_company_access_rules(session, uc.id)
    if not rules:
        return PersonalAccessRules(has_rules=False)

    result = PersonalAccessRules(has_rules=True)
    for rule in rules:
        _apply_rule_to_personal_access(rule, result)

    return result


async def get_actor_section_access(
    session: AsyncSession,
    user_id: UUID,
    company_id: UUID | None,
    role: str,
) -> dict[str, bool]:
    """Return effective section visibility mapping for user and active company.

    If no explicit personal rules are defined, falls back to role default (all True).
    """
    default_access = dict.fromkeys(ALL_SECTION_CODES, True)
    if role == "carcraft_employee" or company_id is None:
        return default_access

    uc = await get_user_company(session, user_id, company_id)
    if uc is None or uc.id is None:
        return default_access

    section_map = await get_user_company_section_access(session, uc.id)
    if not section_map:
        return default_access

    effective = dict(default_access)
    effective.update(section_map)
    return effective


async def check_section_access(
    session: AsyncSession,
    *,
    user_id: UUID,
    company_id: UUID | None,
    role: str,
    section_code: str,
) -> bool:
    """Check if actor's active company has access to a specific section.

    For 'monetization', returns True if either monetization_income or monetization_expense is True.
    """
    if role == "carcraft_employee":
        return True

    access = await get_actor_section_access(session, user_id, company_id, role)
    if section_code == "monetization":
        return bool(access.get("monetization_income", True) or access.get("monetization_expense", True))

    return bool(access.get(section_code, True))


async def check_can_create_employees(
    session: AsyncSession,
    *,
    user_company_id: UUID,
    sub_role: str | None = None,
    role: str | None = None,
) -> bool:
    """Return True if user has permission to create and configure employees."""
    if role == "carcraft_employee" or sub_role == "administrator":
        return True
    perm = await get_employee_permission(session, user_company_id)
    return bool(perm and perm.can_create_employees)


async def save_full_employee_access(
    session: AsyncSession,
    *,
    user_company_id: UUID,
    target_user_id: UUID,
    rules: list[dict[str, Any]],
    sections: dict[str, bool],
    can_create_employees: bool,
    additional_phone: str | None,
    granter_user_id: UUID,
) -> None:
    """Atomically save employee's phone, access rules, sections, and permissions."""
    now = datetime.now(UTC)

    # 1. Update user additional_phone
    user = await session.get(User, target_user_id)
    if user is not None:
        user.additional_phone = additional_phone
        cast("Any", user).updated_at = now

    # 2. Sync user_company_access_rules: delete existing and insert new
    del_stmt = sa.delete(UserCompanyAccessRule).where(
        UserCompanyAccessRule.user_company_id == user_company_id
    )
    await session.execute(del_stmt)

    for r in rules:
        access_obj = str(r.get("access_object", ""))
        access_type = str(r.get("access_type", "all"))
        if not access_obj or not access_type:
            continue
        obj_id = r.get("object_id")
        obj_id_str = str(obj_id) if obj_id is not None else None
        obj_name = r.get("object_name")
        obj_name_str = str(obj_name) if obj_name is not None else None

        rule_row = UserCompanyAccessRule(
            id=uuid.uuid4(),
            user_company_id=user_company_id,
            access_object=access_obj,
            access_type=access_type,
            object_id=obj_id_str,
            object_name=obj_name_str,
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        session.add(rule_row)

    # 3. Upsert user_company_section_access for all 9 sections
    for sec_code in ALL_SECTION_CODES:
        can_view = bool(sections.get(sec_code, True))
        sec_stmt = select(UserCompanySectionAccess).where(
            UserCompanySectionAccess.user_company_id == user_company_id,
            UserCompanySectionAccess.section_code == sec_code,
        )
        existing_sec = (await session.execute(sec_stmt)).scalar_one_or_none()
        if existing_sec is None:
            new_sec = UserCompanySectionAccess(
                id=uuid.uuid4(),
                user_company_id=user_company_id,
                section_code=sec_code,
                can_view=can_view,
                created_at=now,
                updated_at=now,
            )
            session.add(new_sec)
        else:
            existing_sec.can_view = can_view
            existing_sec.updated_at = now

    # 4. Upsert user_company_employee_permissions
    perm_stmt = select(UserCompanyEmployeePermission).where(
        UserCompanyEmployeePermission.user_company_id == user_company_id
    )
    perm = (await session.execute(perm_stmt)).scalar_one_or_none()
    if perm is None:
        perm = UserCompanyEmployeePermission(
            id=uuid.uuid4(),
            user_company_id=user_company_id,
            can_create_employees=can_create_employees,
            granted_by_user_id=granter_user_id if can_create_employees else None,
            granted_at=now if can_create_employees else None,
            created_at=now,
            updated_at=now,
        )
        session.add(perm)
    elif perm.can_create_employees != can_create_employees:
        if can_create_employees:
            perm.granted_by_user_id = granter_user_id
            perm.granted_at = now
        else:
            perm.revoked_by_user_id = granter_user_id
            perm.revoked_at = now
        perm.can_create_employees = can_create_employees
        perm.updated_at = now

    await session.flush()


async def get_user_by_id(session: AsyncSession, user_id: UUID) -> User | None:
    """Retrieve User by primary key."""
    return await session.get(User, user_id)


async def lookup_warehouses(
    session: AsyncSession,
    company_id: UUID,
    q: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Search warehouses belonging to company matching optional query string."""
    conditions = [
        Warehouse.is_active.is_(True),
        Warehouse.owner_company_id == company_id,
    ]
    if q and q.strip():
        search = f"%{q.strip()}%"
        conditions.append(
            sa.or_(Warehouse.name.ilike(search), Warehouse.address.ilike(search))
        )
    stmt = (
        sa.select(Warehouse.id, Warehouse.name, Warehouse.address)
        .where(*conditions)
        .order_by(Warehouse.name.asc())
        .limit(limit)
    )
    rows = (await session.execute(stmt)).all()
    return [{"id": str(r.id), "name": r.name, "address": r.address} for r in rows]


async def lookup_brands(
    session: AsyncSession,
    q: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Search brands/marks matching optional query string."""
    conditions = [SpecialEquipmentMark.is_active.is_(True)]
    if q and q.strip():
        conditions.append(SpecialEquipmentMark.name.ilike(f"%{q.strip()}%"))
    stmt = (
        sa.select(SpecialEquipmentMark.id, SpecialEquipmentMark.name)
        .where(*conditions)
        .order_by(SpecialEquipmentMark.name.asc())
        .limit(limit)
    )
    rows = (await session.execute(stmt)).all()
    return [{"id": str(r.id), "name": r.name} for r in rows]


async def lookup_dealers(
    session: AsyncSession,
    distributor_company_id: UUID,
    q: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Search dealer companies linked to a distributor matching optional query string."""
    conditions = [
        DistributorDealerLink.distributor_company_id == distributor_company_id,
        Company.is_active.is_(True),
    ]
    if q and q.strip():
        search = f"%{q.strip()}%"
        conditions.append(
            sa.or_(Company.name.ilike(search), Company.inn.ilike(search))
        )
    stmt = (
        sa.select(Company.id, Company.name, Company.inn)
        .select_from(DistributorDealerLink)
        .join(Company, Company.id == DistributorDealerLink.dealer_company_id)
        .where(*conditions)
        .order_by(Company.name.asc())
        .limit(limit)
    )
    rows = (await session.execute(stmt)).all()
    return [{"id": str(r.id), "name": r.name, "inn": r.inn} for r in rows]


async def lookup_colleagues(
    session: AsyncSession,
    company_id: UUID,
    exclude_user_id: UUID | None = None,
    q: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Search colleagues of a company matching optional query string, excluding target user."""
    conditions = [
        UserCompany.company_id == company_id,
        UserCompany.is_active.is_(True),
    ]
    if exclude_user_id is not None:
        conditions.append(User.id != exclude_user_id)
    if q and q.strip():
        search = f"%{q.strip()}%"
        conditions.append(
            sa.or_(User.name.ilike(search), User.phone.ilike(search))
        )
    stmt = (
        sa.select(User.id, User.name, User.phone)
        .join(UserCompany, UserCompany.user_id == User.id)
        .where(*conditions)
        .order_by(User.name.asc().nullslast())
        .limit(limit)
    )
    rows = (await session.execute(stmt)).all()
    return [
        {"id": str(r.id), "name": r.name or r.phone, "phone": r.phone}
        for r in rows
    ]
