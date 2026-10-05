"""Employees repository — ORM access for user_companies, users, companies, positions."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.models.companies import Company
from infrastructure.models.positions import Position
from infrastructure.models.support import DealerGroup, DealerGroupMember
from infrastructure.models.user_company_access import UserCompanyEmployeePermission
from infrastructure.models.users import CompanySelectHistory, User, UserCompany


def _row_to_dict(
    *,
    user_id: UUID,
    name: str | None,
    phone: str,
    additional_phone: str | None = None,
    company_id: UUID,
    company_name: str,
    role: str,
    sub_role: str | None,
    position_id: UUID | None,
    position_name: str | None,
    can_view_applications: bool,
    can_create_applications: bool,
    can_create_employees: bool = False,
    is_active: bool,
    created_at: Any,
    updated_at: Any,
    can_edit: bool = True,
) -> dict[str, Any]:
    return {
        "user_id": str(user_id),
        "name": name,
        "phone": phone,
        "additional_phone": additional_phone,
        "company_id": str(company_id),
        "company_name": company_name,
        "role": role,
        "sub_role": sub_role,
        "position_id": str(position_id) if position_id else None,
        "position_name": position_name,
        "can_view_applications": can_view_applications,
        "can_create_applications": can_create_applications,
        "can_create_employees": can_create_employees,
        "is_active": is_active,
        "created_at": created_at,
        "updated_at": updated_at,
        "can_edit": can_edit,
    }


async def _resolve_visible_company_ids(
    session: AsyncSession,
    actor_role: str,
    actor_company_id: UUID | None,
) -> set[UUID] | None:
    """Return visible company IDs for the given actor role, or None if all companies are visible."""
    if actor_role == "carcraft_employee":
        return None
    if actor_company_id is None:
        return set()
    if actor_role == "distributor":
        dg_stmt = (
            sa.select(DealerGroupMember.dealer_company_id)
            .join(DealerGroup, DealerGroup.id == DealerGroupMember.dealer_group_id)
            .where(
                DealerGroup.distributor_company_id == actor_company_id,
                DealerGroup.is_active.is_(True),
            )
        )
        res = await session.execute(dg_stmt)
        dealer_ids = set(res.scalars().all())
        return {actor_company_id} | dealer_ids
    return {actor_company_id}


async def get_active_company_and_role(
    session: AsyncSession,
    user_id: UUID,
    global_role: str,
) -> tuple[UUID | None, str]:
    """Resolve actor's active company ID and active role."""
    if global_role == "carcraft_employee":
        return None, "carcraft_employee"

    history = await session.get(CompanySelectHistory, user_id)
    if history is not None:
        uc = await session.get(UserCompany, (user_id, history.company_id))
        if uc and uc.is_active:
            return history.company_id, uc.role

    user = await session.get(User, user_id)
    if user is not None and user.company_id is not None:
        uc = await session.get(UserCompany, (user_id, user.company_id))
        if uc and uc.is_active:
            return user.company_id, uc.role
        if not uc:
            return user.company_id, user.role or "client"

    stmt = (
        sa.select(UserCompany)
        .where(UserCompany.user_id == user_id, UserCompany.is_active.is_(True))
        .order_by(UserCompany.created_at.desc())
        .limit(1)
    )
    res = (await session.execute(stmt)).scalars().first()
    if res:
        return res.company_id, res.role

    return None, global_role


async def check_can_create_employees(
    session: AsyncSession,
    *,
    actor_user_id: UUID,
    actor_role: str,
    target_company_id: UUID,
) -> bool:
    """Check if actor has permission to create or configure employees in target company."""
    if actor_role == "carcraft_employee":
        return True

    uc = await session.get(UserCompany, (actor_user_id, target_company_id))
    if uc is None or not uc.is_active:
        return False

    perm_stmt = sa.select(UserCompanyEmployeePermission).where(
        UserCompanyEmployeePermission.user_company_id == uc.id
    )
    perm = (await session.execute(perm_stmt)).scalar_one_or_none()
    if perm is not None:
        return bool(perm.can_create_employees)

    return uc.sub_role == "administrator"


async def list_employees(  # noqa: PLR0912
    session: AsyncSession,
    *,
    actor_role: str,
    actor_company_id: UUID | None,
    filter_company_id: UUID | None = None,
    position_id: UUID | None = None,
    name: str | None = None,
    phone: str | None = None,
    role: str | None = None,
    distributor_id: UUID | None = None,
    dealer_id: UUID | None = None,
    brand_id: UUID | None = None,
    warehouse_id: UUID | None = None,
    page: int = 1,
    per_page: int | None = 20,
) -> tuple[list[dict[str, Any]], int]:
    """List employees matching filters, enforcing visibility rules and returning can_edit."""
    visible_company_ids = await _resolve_visible_company_ids(
        session, actor_role, actor_company_id
    )
    if visible_company_ids is not None and not visible_company_ids:
        return [], 0

    conditions: list[Any] = []

    if filter_company_id is not None:
        if (
            visible_company_ids is not None
            and filter_company_id not in visible_company_ids
        ):
            return [], 0
        conditions.append(UserCompany.company_id == filter_company_id)
    elif visible_company_ids is not None:
        conditions.append(UserCompany.company_id.in_(visible_company_ids))

    if position_id is not None:
        conditions.append(UserCompany.position_id == position_id)

    if name and name.strip():
        conditions.append(User.name.ilike(f"%{name.strip()}%"))

    if phone and phone.strip():
        conditions.append(User.phone.ilike(f"%{phone.strip()}%"))

    if role == "carcraft_employee":
        conditions.append(
            sa.cast(User.role, sa.String).in_(["admin", "carcraft_employee"])
        )
    elif role:
        conditions.append(UserCompany.role == role)
    if dealer_id is not None:
        conditions.append(UserCompany.company_id == dealer_id)

    can_create_expr = sa.func.coalesce(
        UserCompanyEmployeePermission.can_create_employees,
        UserCompany.sub_role == "administrator",
    ).label("can_create_employees")

    stmt = (
        sa.select(
            UserCompany.id.label("user_company_id"),
            UserCompany.user_id,
            User.role.label("system_role"),
            User.name.label("user_name"),
            User.phone.label("user_phone"),
            User.additional_phone.label("user_additional_phone"),
            UserCompany.company_id,
            Company.name.label("company_name"),
            UserCompany.role,
            UserCompany.sub_role,
            UserCompany.position_id,
            Position.name.label("position_name"),
            UserCompany.can_view_applications,
            UserCompany.can_create_applications,
            can_create_expr,
            UserCompany.is_active,
            UserCompany.created_at,
            UserCompany.updated_at,
        )
        .join(User, User.id == UserCompany.user_id)
        .join(Company, Company.id == UserCompany.company_id)
        .outerjoin(Position, Position.id == UserCompany.position_id)
        .outerjoin(
            UserCompanyEmployeePermission,
            UserCompanyEmployeePermission.user_company_id == UserCompany.id,
        )
        .where(*conditions)
        .order_by(
            UserCompany.created_at.desc().nullslast(),
            User.name.asc().nullslast(),
            UserCompany.id,
        )
    )

    rows = (await session.execute(stmt)).all()

    items: list[dict[str, Any]] = [
        _row_to_dict(
            user_id=r.user_id,
            name=r.user_name,
            phone=r.user_phone,
            additional_phone=r.user_additional_phone,
            company_id=r.company_id,
            company_name=r.company_name,
            role=r.role,
            sub_role=r.sub_role,
            position_id=r.position_id,
            position_name=r.position_name,
            can_view_applications=r.can_view_applications,
            can_create_applications=r.can_create_applications,
            can_create_employees=bool(r.can_create_employees),
            is_active=r.is_active,
            created_at=r.created_at,
            updated_at=r.updated_at,
            can_edit=(
                bool(actor_company_id and r.company_id == actor_company_id)
                if actor_role == "distributor"
                else True
            ),
        )
        for r in rows
    ]

    for item, row in zip(items, rows, strict=True):
        item.update(
            row_type="company",
            user_company_id=str(row.user_company_id),
            company_role=row.role,
        )
    from infrastructure.repositories.employee_list_objects import (
        hydrate_employee_objects,
    )

    await hydrate_employee_objects(session, items)
    for item, row in zip(items, rows, strict=True):
        if row.system_role in ("admin", "carcraft_employee"):
            item["role"] = "carcraft_employee"
    items = [
        item
        for item in items
        if all(
            selected is None or str(selected) in {obj["id"] for obj in item[key]}
            for selected, key in (
                (distributor_id, "distributors"),
                (brand_id, "brands"),
                (warehouse_id, "warehouses"),
            )
        )
    ]
    if (
        actor_role == "carcraft_employee"
        and role in (None, "carcraft_employee")
        and not any(
            (
                filter_company_id,
                position_id,
                dealer_id,
                distributor_id,
                brand_id,
                warehouse_id,
            )
        )
    ):
        conditions_system = [
            sa.cast(User.role, sa.String).in_(["admin", "carcraft_employee"]),
            ~sa.exists().where(UserCompany.user_id == User.id),
        ]
        if name and name.strip():
            conditions_system.append(User.name.ilike(f"%{name.strip()}%"))
        if phone and phone.strip():
            conditions_system.append(User.phone.ilike(f"%{phone.strip()}%"))
        users = (
            (await session.execute(sa.select(User).where(*conditions_system)))
            .scalars()
            .all()
        )
        for user in users:
            items.append(
                {
                    "row_type": "system",
                    "user_company_id": None,
                    "company_role": None,
                    "user_id": str(user.id),
                    "name": user.name,
                    "phone": user.phone,
                    "additional_phone": user.additional_phone,
                    "company_id": None,
                    "company_name": None,
                    "role": "carcraft_employee",
                    "sub_role": None,
                    "position_id": None,
                    "position_name": None,
                    "can_view_applications": False,
                    "can_create_applications": False,
                    "can_create_employees": False,
                    "is_active": bool(user.is_active),
                    "created_at": user.created_at,
                    "updated_at": user.updated_at,
                    "can_edit": False,
                    "brands": [],
                    "warehouses": [],
                    "distributors": [],
                }
            )
    # A unique typed row key closes ordering, including company-less system users.
    items.sort(
        key=lambda item: (
            -(item["created_at"].timestamp() if item["created_at"] else float("-inf")),
            item["name"] or "\uffff",
            item["row_type"],
            item["user_company_id"]
            if item["row_type"] == "company"
            else item["user_id"],
        )
    )
    total = len(items)
    if per_page is None:
        return items, total
    offset = (page - 1) * per_page
    return items[offset : offset + per_page], total


async def get_employee(
    session: AsyncSession,
    user_id: UUID,
    company_id: UUID,
    *,
    can_edit: bool = True,
) -> dict[str, Any] | None:
    """Fetch a single employee by user_id and company_id."""
    can_create_expr = sa.func.coalesce(
        UserCompanyEmployeePermission.can_create_employees,
        UserCompany.sub_role == "administrator",
    ).label("can_create_employees")

    stmt = (
        sa.select(
            UserCompany.user_id,
            User.name.label("user_name"),
            User.phone.label("user_phone"),
            User.additional_phone.label("user_additional_phone"),
            UserCompany.company_id,
            Company.name.label("company_name"),
            UserCompany.role,
            UserCompany.sub_role,
            UserCompany.position_id,
            Position.name.label("position_name"),
            UserCompany.can_view_applications,
            UserCompany.can_create_applications,
            can_create_expr,
            UserCompany.is_active,
            UserCompany.created_at,
            UserCompany.updated_at,
        )
        .join(User, User.id == UserCompany.user_id)
        .join(Company, Company.id == UserCompany.company_id)
        .outerjoin(Position, Position.id == UserCompany.position_id)
        .outerjoin(
            UserCompanyEmployeePermission,
            UserCompanyEmployeePermission.user_company_id == UserCompany.id,
        )
        .where(
            UserCompany.user_id == user_id,
            UserCompany.company_id == company_id,
        )
    )
    row = (await session.execute(stmt)).first()
    if row is None:
        return None

    return _row_to_dict(
        user_id=row.user_id,
        name=row.user_name,
        phone=row.user_phone,
        additional_phone=row.user_additional_phone,
        company_id=row.company_id,
        company_name=row.company_name,
        role=row.role,
        sub_role=row.sub_role,
        position_id=row.position_id,
        position_name=row.position_name,
        can_view_applications=row.can_view_applications,
        can_create_applications=row.can_create_applications,
        can_create_employees=bool(row.can_create_employees),
        is_active=row.is_active,
        created_at=row.created_at,
        updated_at=row.updated_at,
        can_edit=can_edit,
    )


async def upsert_employee(  # noqa: PLR0912, PLR0915
    session: AsyncSession,
    *,
    name: str,
    phone: str,
    additional_phone: str | None = None,
    company_id: UUID,
    role: str,
    position_id: UUID | None,
    can_view_applications: bool,
    can_create_applications: bool,
    can_create_employees: bool = False,
    is_active: bool,
    granter_user_id: UUID | None = None,
) -> dict[str, Any]:
    """Create or update a user and link them to the target company."""
    company = await session.get(Company, company_id)
    if (
        role == "client"
        and company
        and company.company_type in {"dealer", "distributor", "leasing_company"}
    ):
        role = company.company_type

    user_stmt = sa.select(User).where(User.phone == phone)
    user = (await session.execute(user_stmt)).scalar_one_or_none()
    now = datetime.now(UTC)

    if user is None:
        user = User(
            phone=phone,
            additional_phone=additional_phone,
            name=name,
            role=role,
            is_active=True,
            company_id=company_id,
        )
        cast("Any", user).created_at = now
        cast("Any", user).updated_at = now
        session.add(user)
        await session.flush()
    else:
        if name:
            user.name = name
        if additional_phone is not None:
            user.additional_phone = additional_phone
        if user.company_id is None:
            user.company_id = company_id
        if user.role == "client" and role in {"dealer", "distributor"}:
            user.role = role
        cast("Any", user).updated_at = now
        await session.flush()

    user_id = user.id

    uc = await session.get(UserCompany, (user_id, company_id))
    if uc is None:
        uc = UserCompany(
            id=uuid.uuid4(),
            user_id=user_id,
            company_id=company_id,
            role=role,
            sub_role="employee",
            position_id=position_id,
            can_view_applications=can_view_applications,
            can_create_applications=can_create_applications,
            is_active=is_active,
        )
        cast("Any", uc).created_at = now
        cast("Any", uc).updated_at = now
        session.add(uc)
    else:
        uc.role = role
        uc.position_id = position_id
        uc.can_view_applications = can_view_applications
        uc.can_create_applications = can_create_applications
        uc.is_active = is_active
        cast("Any", uc).updated_at = now

    await session.flush()

    # Manage can_create_employees permission
    perm_stmt = sa.select(UserCompanyEmployeePermission).where(
        UserCompanyEmployeePermission.user_company_id == uc.id
    )
    perm = (await session.execute(perm_stmt)).scalar_one_or_none()
    if perm is None:
        perm = UserCompanyEmployeePermission(
            id=uuid.uuid4(),
            user_company_id=uc.id,
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

    history = await session.get(CompanySelectHistory, user_id)
    if history is None:
        history = CompanySelectHistory(
            user_id=user_id,
            company_id=company_id,
        )
        cast("Any", history).updated_at = now
        session.add(history)

    await session.flush()

    emp = await get_employee(session, user_id, company_id)
    if emp is None:
        company = await session.get(Company, company_id)
        return _row_to_dict(
            user_id=user_id,
            name=user.name,
            phone=user.phone,
            additional_phone=user.additional_phone,
            company_id=company_id,
            company_name=company.name if company else "",
            role=uc.role,
            sub_role=uc.sub_role,
            position_id=position_id,
            position_name=None,
            can_view_applications=uc.can_view_applications,
            can_create_applications=uc.can_create_applications,
            can_create_employees=can_create_employees,
            is_active=uc.is_active,
            created_at=getattr(uc, "created_at", None),
            updated_at=getattr(uc, "updated_at", None),
            can_edit=True,
        )
    return emp


async def update_employee(
    session: AsyncSession,
    *,
    user_id: UUID,
    company_id: UUID,
    name: str | None,
    phone: str | None = None,
    additional_phone: str | None = None,
    role: str,
    position_id: UUID | None,
    can_view_applications: bool,
    can_create_applications: bool,
    can_create_employees: bool | None = None,
    is_active: bool,
    granter_user_id: UUID | None = None,
) -> dict[str, Any] | None:
    """Update employee user name, phones, and user_companies link row."""
    del phone
    uc = await session.get(UserCompany, (user_id, company_id))
    if uc is None:
        return None

    now = datetime.now(UTC)
    user = await session.get(User, user_id)
    if user is not None:
        if name is not None and name.strip():
            user.name = name.strip()
        if additional_phone is not None:
            user.additional_phone = additional_phone
        cast("Any", user).updated_at = now

    uc.role = role
    uc.position_id = position_id
    uc.can_view_applications = can_view_applications
    uc.can_create_applications = can_create_applications
    uc.is_active = is_active
    cast("Any", uc).updated_at = now

    if can_create_employees is not None:
        perm_stmt = sa.select(UserCompanyEmployeePermission).where(
            UserCompanyEmployeePermission.user_company_id == uc.id
        )
        perm = (await session.execute(perm_stmt)).scalar_one_or_none()
        if perm is None:
            perm = UserCompanyEmployeePermission(
                id=uuid.uuid4(),
                user_company_id=uc.id,
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
    return await get_employee(session, user_id, company_id)


async def deactivate_employee(
    session: AsyncSession,
    *,
    user_id: UUID,
    company_id: UUID,
) -> bool:
    """Soft-deactivate an employee link (user_companies.is_active = False).

    Never modifies User.is_active.
    """
    uc = await session.get(UserCompany, (user_id, company_id))
    if uc is None:
        return False

    uc.is_active = False
    cast("Any", uc).updated_at = datetime.now(UTC)
    await session.flush()
    return True
