"""Employees query handlers (task 21674 & task 21952).

Handles listing employees, viewing access settings, and lookups for access configuration.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.errors import ServiceError
from infrastructure.repositories import employees_repository
from infrastructure.repositories.user_company_access_repository import (
    ALL_SECTION_CODES,
    get_employee_permission,
    get_user_by_id,
    get_user_company_access_rules,
    get_user_company_by_user_and_company,
    get_user_company_section_access,
    lookup_brands,
    lookup_colleagues,
    lookup_dealers,
    lookup_warehouses,
)


@dataclass
class ListEmployeesQuery:
    actor_user_id: UUID
    actor_role: str
    actor_company_id: UUID | None
    filter_company_id: UUID | None = None
    position_id: UUID | None = None
    name: str | None = None
    phone: str | None = None
    role: str | None = None
    distributor_id: UUID | None = None
    dealer_id: UUID | None = None
    brand_id: UUID | None = None
    warehouse_id: UUID | None = None
    page: int = 1
    per_page: int | None = 20


@dataclass
class GetEmployeeQuery:
    actor_user_id: UUID
    actor_role: str
    actor_company_id: UUID | None
    user_id: UUID
    company_id: UUID


@dataclass
class GetEmployeeAccessSettingsQuery:
    actor_user_id: UUID
    actor_role: str
    actor_company_id: UUID | None
    user_id: UUID
    company_id: UUID


@dataclass
class LookupWarehousesQuery:
    actor_user_id: UUID
    actor_role: str
    actor_company_id: UUID | None
    company_id: UUID
    q: str | None = None
    limit: int = 50


@dataclass
class LookupBrandsQuery:
    actor_user_id: UUID
    actor_role: str
    actor_company_id: UUID | None
    company_id: UUID
    q: str | None = None
    limit: int = 50


@dataclass
class LookupDealersQuery:
    actor_user_id: UUID
    actor_role: str
    actor_company_id: UUID | None
    distributor_company_id: UUID
    q: str | None = None
    limit: int = 50


@dataclass
class LookupColleaguesQuery:
    actor_user_id: UUID
    actor_role: str
    actor_company_id: UUID | None
    company_id: UUID
    exclude_user_id: UUID | None = None
    q: str | None = None
    limit: int = 50


async def handle_list_employees(
    query: ListEmployeesQuery, session: AsyncSession
) -> tuple[list[dict[str, Any]], int]:
    """Return paginated list of employees accessible by actor."""
    if ((query.distributor_id or query.dealer_id) and query.role != "dealer") or (
        (query.brand_id or query.warehouse_id)
        and query.role not in ("dealer", "distributor")
    ):
        raise ServiceError("Объектные фильтры несовместимы с выбранной ролью", 422)
    active_company_id = query.actor_company_id
    active_role = query.actor_role
    if active_role != "carcraft_employee" and active_company_id is None:
        (
            active_company_id,
            active_role,
        ) = await employees_repository.get_active_company_and_role(
            session, query.actor_user_id, query.actor_role
        )

    return await employees_repository.list_employees(
        session,
        actor_role=active_role,
        actor_company_id=active_company_id,
        filter_company_id=query.filter_company_id,
        position_id=query.position_id,
        name=query.name,
        phone=query.phone,
        role=query.role,
        distributor_id=query.distributor_id,
        dealer_id=query.dealer_id,
        brand_id=query.brand_id,
        warehouse_id=query.warehouse_id,
        page=query.page,
        per_page=query.per_page,
    )


async def handle_get_employee(
    query: GetEmployeeQuery, session: AsyncSession
) -> dict[str, Any]:
    """Return a single employee accessible by actor."""
    active_company_id = query.actor_company_id
    active_role = query.actor_role
    if active_role != "carcraft_employee" and active_company_id is None:
        (
            active_company_id,
            active_role,
        ) = await employees_repository.get_active_company_and_role(
            session, query.actor_user_id, query.actor_role
        )

    can_edit = True
    if active_role == "distributor":
        can_edit = bool(active_company_id and query.company_id == active_company_id)

    emp = await employees_repository.get_employee(
        session,
        user_id=query.user_id,
        company_id=query.company_id,
        can_edit=can_edit,
    )
    if emp is None:
        raise ServiceError("Сотрудник не найден", 404)
    return emp


async def handle_get_employee_access_settings(
    query: GetEmployeeAccessSettingsQuery, session: AsyncSession
) -> dict[str, Any]:
    """Return an employee's personal access settings along with selector options."""
    active_company_id = query.actor_company_id
    active_role = query.actor_role
    if active_role != "carcraft_employee" and active_company_id is None:
        (
            active_company_id,
            active_role,
        ) = await employees_repository.get_active_company_and_role(
            session, query.actor_user_id, query.actor_role
        )

    target_uc = await get_user_company_by_user_and_company(
        session, query.user_id, query.company_id
    )
    if target_uc is None:
        raise ServiceError("Сотрудник не найден", 404)

    target_user = await get_user_by_id(session, query.user_id)
    if target_user is None:
        raise ServiceError("Пользователь не найден", 404)

    # Permissions of granter (actor)
    granter_can_create = False
    if active_role == "carcraft_employee":
        granter_can_create = True
    elif active_company_id is not None:
        granter_can_create = await employees_repository.check_can_create_employees(
            session,
            actor_user_id=query.actor_user_id,
            actor_role=active_role,
            target_company_id=active_company_id,
        )

    # Actor cannot edit own permissions
    is_self = query.actor_user_id == query.user_id
    can_edit = granter_can_create and not is_self
    if active_role == "distributor" and active_company_id != query.company_id:
        can_edit = False

    # Target settings
    rules = await get_user_company_access_rules(session, target_uc.id)
    custom_sections = await get_user_company_section_access(session, target_uc.id)
    sections = {code: custom_sections.get(code, True) for code in ALL_SECTION_CODES}

    perm = await get_employee_permission(session, target_uc.id)
    target_can_create = (
        bool(perm.can_create_employees)
        if perm is not None
        else (target_uc.sub_role == "administrator")
    )

    # Granter's available sections
    available_sections = list(ALL_SECTION_CODES)
    if active_role != "carcraft_employee":
        granter_uc = await get_user_company_by_user_and_company(
            session, query.actor_user_id, query.company_id
        )
        if granter_uc is not None:
            g_sections = await get_user_company_section_access(session, granter_uc.id)
            available_sections = [
                code for code in ALL_SECTION_CODES if g_sections.get(code, True)
            ]

    # Prepopulate available objects for granter
    available_warehouses = await lookup_warehouses(session, query.company_id, limit=100)
    available_brands = await lookup_brands(session, limit=100)
    available_dealers: list[dict[str, Any]] = []
    if target_uc.role == "distributor":
        available_dealers = await lookup_dealers(session, query.company_id, limit=100)
    available_colleagues = await lookup_colleagues(session, query.company_id, limit=100)

    return {
        "user_company_id": target_uc.id,
        "user_id": query.user_id,
        "company_id": query.company_id,
        "can_create_employees": target_can_create,
        "additional_phone": target_user.additional_phone,
        "rules": [
            {
                "id": r.id,
                "access_object": r.access_object,
                "access_type": r.access_type,
                "object_id": r.object_id,
                "object_name": r.object_name,
                "is_active": r.is_active,
            }
            for r in rules
        ],
        "sections": sections,
        "available_objects": {
            "warehouses": available_warehouses,
            "brands": available_brands,
            "dealers": available_dealers,
            "colleagues": available_colleagues,
        },
        "available_sections": available_sections,
        "granter_can_create_employees": granter_can_create,
        "can_edit": can_edit,
    }


async def handle_lookup_warehouses(
    query: LookupWarehousesQuery, session: AsyncSession
) -> dict[str, Any]:
    """Search warehouses belonging to company matching optional query string."""
    items = await lookup_warehouses(
        session, query.company_id, q=query.q, limit=query.limit
    )
    return {"items": items, "total": len(items)}


async def handle_lookup_brands(
    query: LookupBrandsQuery, session: AsyncSession
) -> dict[str, Any]:
    """Search brands/marks matching optional query string."""
    items = await lookup_brands(session, q=query.q, limit=query.limit)
    return {"items": items, "total": len(items)}


async def handle_lookup_dealers(
    query: LookupDealersQuery, session: AsyncSession
) -> dict[str, Any]:
    """Search dealer companies linked to a distributor matching optional query string."""
    items = await lookup_dealers(
        session, query.distributor_company_id, q=query.q, limit=query.limit
    )
    return {"items": items, "total": len(items)}


async def handle_lookup_colleagues(
    query: LookupColleaguesQuery, session: AsyncSession
) -> dict[str, Any]:
    """Search colleagues of a company matching optional query string, excluding target user."""
    items = await lookup_colleagues(
        session,
        query.company_id,
        exclude_user_id=query.exclude_user_id,
        q=query.q,
        limit=query.limit,
    )
    return {"items": items, "total": len(items)}


async def handle_employee_filter_options(
    query: ListEmployeesQuery, session: AsyncSession
) -> dict[str, Any]:
    """Return full visible selector sets independently of the current employee page."""
    query.per_page = None
    items, _ = await handle_list_employees(query, session)
    options: dict[str, dict[str, dict[str, str]]] = {
        key: {}
        for key in ("companies", "dealers", "distributors", "brands", "warehouses")
    }
    for item in items:
        if item["company_id"]:
            company = {"id": item["company_id"], "name": item["company_name"]}
            options["companies"][company["id"]] = company
            if item["company_role"] == "dealer":
                options["dealers"][company["id"]] = company
        for key in ("distributors", "brands", "warehouses"):
            for obj in item[key]:
                options[key][obj["id"]] = obj
    return {
        key: sorted(values.values(), key=lambda obj: (obj["name"], obj["id"]))
        for key, values in options.items()
    }
