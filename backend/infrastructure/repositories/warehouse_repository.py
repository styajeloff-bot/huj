"""Warehouse repository — async, dict-only API.

Covers warehouses, vehicle ↔ warehouse bindings and the bind-by-mark
mass-attach helper. Uses ORM models from `infrastructure.models.vehicles`
and reads `mark` for bind-by-mark validation.
"""
from __future__ import annotations

import contextlib
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import (
    String,
    and_,
    false,
    func,
    literal,
    or_,
    select,
    text,
    union_all,
    update,
)
from sqlalchemy import cast as sql_cast
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from domain.values import WarehouseStatus
from infrastructure.models.companies import Company
from infrastructure.models.exchange import (
    ExchangeCartItemWarehouse,
    ExchangeRequestWarehouse,
)
from infrastructure.models.special_equipment import (
    SpecialEquipmentCategory,
    SpecialEquipmentMark,
    SpecialEquipmentModel,
    SpecialEquipmentModification,
    SpecialEquipmentModificationCategory,
    SpecialEquipmentProduct,
)
from infrastructure.models.special_equipment_import import SpecialEquipmentImportJob
from infrastructure.models.storefronts import Storefront, StorefrontWarehouse
from infrastructure.models.support import DealerGroup
from infrastructure.models.users import User
from infrastructure.models.vehicles import (
    City,
    VehicleWarehouseTransfer,
    Warehouse,
    WarehouseAccessRule,
    WarehouseMark,
)
from infrastructure.repositories.vehicle_stock_status_repository import (
    enrich_stock_status,
)
from infrastructure.repository_timing import timed_repository


class WarehouseBindingTargetUnavailableError(Exception):
    """The warehouse disappeared while a vehicle binding was inserted."""


def _is_binding_warehouse_integrity_error(exc: IntegrityError) -> bool:
    original = exc.orig
    diagnostic = getattr(original, "diag", None)
    constraint_name = getattr(original, "constraint_name", None) or getattr(
        diagnostic, "constraint_name", None
    )
    return (
        getattr(original, "sqlstate", None) == "23503"
        and constraint_name == "vehicle_warehouses_warehouse_id_fkey"
    )


def _warehouse_scope_conditions(dealer_filter: list[UUID] | None) -> list[Any]:
    """Return the effective-owner/access predicate for role-scoped warehouse reads.

    If dealer_filter is None (admin), all warehouses are visible.
    If dealer_filter is empty list, no warehouses are visible.
    If dealer_filter is populated (dealer or distributor companies), visible warehouses are:
    1. Owned by actor's companies (owner_company_id in dealer_filter).
    2. Accessible via active warehouse_access_rules (target_id in dealer_filter and is_active is True).
    """
    if dealer_filter is None:
        return []
    if not dealer_filter:
        return [false()]
    return [
        or_(
            Warehouse.owner_company_id.in_(dealer_filter),
            Warehouse.id.in_(
                select(WarehouseAccessRule.warehouse_id).where(
                    WarehouseAccessRule.target_id.in_(dealer_filter),
                    WarehouseAccessRule.is_active.is_(True),
                )
            ),
        )
    ]


def _row_to_dict(
    row: Warehouse,
    *,
    city_name: str | None = None,
    owner_company_name: str | None = None,
    brand_name: str | None = None,
    selected_brands: list[dict[str, Any]] | None = None,
    category_name: str | None = None,
    warehouse_access_type: str = "A",
    groups: list[str] | None = None,
    vehicles_count: int = 0,
    vehicle_types: list[str] | None = None,
    sites: list[str] | None = None,
    vehicle_marks: list[str] | None = None,
) -> dict[str, Any]:
    marks = vehicle_marks or []
    return {
        "id": row.id,
        "name": row.name,
        "owner_company_id": row.owner_company_id,
        "owner_company_type": row.owner_company_type,
        "owner_company_name": owner_company_name,
        "address": row.address,
        "city_id": row.city_id,
        "city_name": city_name,
        "brand_ids": [brand["id"] for brand in selected_brands or []],
        "selected_brands": selected_brands or [],
        "category_id": row.category_id,
        "category_name": category_name,
        "brand_name": brand_name,
        "brands": marks,
        "vehicle_marks": marks,
        "is_active": row.is_active,
        "warehouse_access_type": warehouse_access_type,
        "groups": groups or [],
        "vehicles_count": vehicles_count,
        "vehicle_types": vehicle_types or [],
        "sites": sites or [],
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        # Legacy backward-compatibility aliases:
        "company_id": row.owner_company_id,
        "company_name": owner_company_name,
        "dealer_id": row.owner_company_id if row.owner_company_type == "dealer" else None,
        "dealer_name": owner_company_name if row.owner_company_type == "dealer" else None,
        "brand": brand_name or "",
        "status": "active" if row.is_active else "inactive",
    }


async def _compute_access_type(
    session: AsyncSession,
    warehouse_id: UUID,
    *,
    is_admin: bool,
    is_owner: bool,
    company_id: UUID | None = None,
    owner_company_id: UUID | None = None,
    actor_filter: list[UUID] | None = None,
    actor_role: str | None = None,
) -> str:
    if is_admin or is_owner or (company_id is not None and owner_company_id is not None and owner_company_id == company_id):
        return "A"

    target_ids = [company_id] if company_id is not None else (actor_filter or [])
    rules_stmt = select(WarehouseAccessRule.warehouse_access_type).where(
        WarehouseAccessRule.warehouse_id == warehouse_id,
        WarehouseAccessRule.is_active.is_(True),
        WarehouseAccessRule.target_id.in_(target_ids),
    )
    rule_types = set((await session.execute(rules_stmt)).scalars().all())
    rule_types.discard("A")

    if actor_role == "distributor" and company_id is not None and actor_filter:
        linked_dealer_ids = {d for d in actor_filter if d != company_id}
        if owner_company_id is not None and owner_company_id in linked_dealer_ids:
            return "C" if ("C" in rule_types and "B" not in rule_types) else "B"

    return "B" if "B" in rule_types else "C"


async def _compute_vehicles_and_types(
    session: AsyncSession,
    row: Warehouse,
    *,
    is_admin: bool,
    is_owner: bool,
    actor_filter: list[UUID] | None,
    company_id: UUID | None = None,
) -> tuple[int, list[str]]:
    prod_stmt = select(
        func.count(SpecialEquipmentProduct.id).label("cnt"),
        SpecialEquipmentProduct.condition,
    ).where(
        SpecialEquipmentProduct.warehouse_id == row.id,
        SpecialEquipmentProduct.publication_status == "published",
        SpecialEquipmentProduct.sale_status == "available",
    )

    rule_brand_ids: list[UUID] = []
    if actor_filter and not is_admin and not is_owner:
        target_ids = [company_id] if company_id is not None else actor_filter
        rules_for_brand_stmt = select(WarehouseAccessRule).where(
            WarehouseAccessRule.warehouse_id == row.id,
            WarehouseAccessRule.is_active.is_(True),
            WarehouseAccessRule.target_id.in_(target_ids),
        )
        actor_active_rules = list((await session.execute(rules_for_brand_stmt)).scalars().all())
        has_unrestricted_brand = any(r.brand_id is None for r in actor_active_rules)
        if actor_active_rules and not has_unrestricted_brand:
            rule_brand_ids = [r.brand_id for r in actor_active_rules if r.brand_id is not None]

    if rule_brand_ids:
        prod_stmt = (
            prod_stmt
            .outerjoin(
                SpecialEquipmentModification,
                SpecialEquipmentModification.id == SpecialEquipmentProduct.modification_id,
            )
            .join(
                SpecialEquipmentModel,
                SpecialEquipmentModel.id
                == sa.func.coalesce(
                    SpecialEquipmentModification.model_id,
                    SpecialEquipmentProduct.model_id,
                ),
            )
            .where(SpecialEquipmentModel.mark_id.in_(rule_brand_ids))
        )

    prod_stmt = prod_stmt.group_by(SpecialEquipmentProduct.condition)
    cond_counts = (await session.execute(prod_stmt)).all()
    vehicles_count = sum(c[0] for c in cond_counts)

    raw_conditions = {c[1] for c in cond_counts if c[1]}
    vehicle_types: list[str] = []
    if "new" in raw_conditions:
        vehicle_types.append("Новые")
    if "used" in raw_conditions:
        vehicle_types.append("Б/У")

    return int(vehicles_count), vehicle_types


def _build_access_type_condition(  # noqa: PLR0911
    dealer_filter: list[UUID] | None,
    access_type: str,
    *,
    company_id: UUID | None = None,
    actor_role: str | None = None,
) -> Any:
    norm_type = access_type.upper()
    if dealer_filter is None:  # Admin
        return false() if norm_type != "A" else None

    target_ids = [company_id] if company_id is not None else dealer_filter
    rule_target_pred = WarehouseAccessRule.target_id.in_(target_ids)

    rule_b_subquery = select(WarehouseAccessRule.warehouse_id).where(
        rule_target_pred,
        WarehouseAccessRule.is_active.is_(True),
        WarehouseAccessRule.warehouse_access_type == "B",
    )
    rule_c_subquery = select(WarehouseAccessRule.warehouse_id).where(
        rule_target_pred,
        WarehouseAccessRule.is_active.is_(True),
        WarehouseAccessRule.warehouse_access_type == "C",
    )

    if norm_type == "A":
        if company_id is not None:
            return Warehouse.owner_company_id == company_id
        return Warehouse.owner_company_id.in_(dealer_filter)

    if norm_type == "B":
        if actor_role == "distributor" and company_id is not None:
            dealer_ids = [d for d in dealer_filter if d != company_id]
            return and_(
                Warehouse.owner_company_id != company_id,
                or_(
                    and_(
                        Warehouse.owner_company_id.in_(dealer_ids),
                        Warehouse.id.not_in(
                            select(WarehouseAccessRule.warehouse_id).where(
                                rule_target_pred,
                                WarehouseAccessRule.is_active.is_(True),
                                WarehouseAccessRule.warehouse_access_type == "C",
                                WarehouseAccessRule.warehouse_id.not_in(rule_b_subquery),
                            )
                        ),
                    ),
                    Warehouse.id.in_(rule_b_subquery),
                ),
            )
        return and_(
            Warehouse.owner_company_id != company_id if company_id is not None else Warehouse.owner_company_id.not_in(dealer_filter),
            Warehouse.id.in_(rule_b_subquery),
        )

    if norm_type == "C":
        owner_pred = (
            Warehouse.owner_company_id != company_id
            if company_id is not None
            else Warehouse.owner_company_id.not_in(dealer_filter)
        )
        if actor_role == "distributor" and company_id is not None:
            dealer_ids = [d for d in dealer_filter if d != company_id]
            return and_(
                owner_pred,
                or_(
                    and_(
                        Warehouse.owner_company_id.in_(dealer_ids),
                        Warehouse.id.in_(rule_c_subquery),
                        Warehouse.id.not_in(rule_b_subquery),
                    ),
                    and_(
                        Warehouse.owner_company_id.not_in(dealer_ids),
                        Warehouse.id.in_(rule_c_subquery),
                        Warehouse.id.not_in(rule_b_subquery),
                    ),
                ),
            )
        return and_(
            owner_pred,
            Warehouse.id.in_(rule_c_subquery),
            Warehouse.id.not_in(rule_b_subquery),
        )

    return None


@timed_repository
async def _hydrate(
    session: AsyncSession,
    row: Warehouse,
    *,
    actor_filter: list[UUID] | None = None,
    is_admin: bool = False,
    company_id: UUID | None = None,
    actor_role: str | None = None,
) -> dict[str, Any]:
    city_name: str | None = None
    if row.city_id is not None:
        city = await session.get(City, row.city_id)
        if city is not None:
            city_name = city.name

    owner_company_name: str | None = None
    if row.owner_company_id is not None:
        company = await session.get(Company, row.owner_company_id)
        if company is not None:
            owner_company_name = company.name

    selected_brands = await get_selected_brands(session, row.id)
    category_name = await session.scalar(
        select(SpecialEquipmentCategory.name).where(SpecialEquipmentCategory.id == row.category_id)
    ) if row.category_id is not None else None

    effective_company_id = company_id
    if effective_company_id is None and actor_filter is not None and len(actor_filter) == 1 and not is_admin:
        effective_company_id = actor_filter[0]

    is_owner = (
        effective_company_id is not None
        and row.owner_company_id == effective_company_id
    )

    # Calculate marks of vehicles on the warehouse from SpecialEquipmentProduct
    marks_stmt = (
        select(SpecialEquipmentMark.name)
        .select_from(SpecialEquipmentProduct)
        .outerjoin(
            SpecialEquipmentModification,
            SpecialEquipmentModification.id == SpecialEquipmentProduct.modification_id,
        )
        .join(
            SpecialEquipmentModel,
            SpecialEquipmentModel.id
            == sa.func.coalesce(
                SpecialEquipmentModification.model_id,
                SpecialEquipmentProduct.model_id,
            ),
        )
        .join(
            SpecialEquipmentMark,
            SpecialEquipmentMark.id == SpecialEquipmentModel.mark_id,
        )
        .where(SpecialEquipmentProduct.warehouse_id == row.id)
    )

    if not is_admin and not is_owner:
        marks_stmt = marks_stmt.where(
            SpecialEquipmentProduct.publication_status == "published",
            SpecialEquipmentProduct.sale_status == "available",
        )
        target_ids = [effective_company_id] if effective_company_id is not None else (actor_filter or [])
        if target_ids:
            rules_for_brand_stmt = select(WarehouseAccessRule).where(
                WarehouseAccessRule.warehouse_id == row.id,
                WarehouseAccessRule.is_active.is_(True),
                WarehouseAccessRule.target_id.in_(target_ids),
            )
            actor_active_rules = list((await session.execute(rules_for_brand_stmt)).scalars().all())
            has_unrestricted_brand = any(r.brand_id is None for r in actor_active_rules)
            if actor_active_rules and not has_unrestricted_brand:
                rule_brand_ids = [r.brand_id for r in actor_active_rules if r.brand_id is not None]
                if rule_brand_ids:
                    marks_stmt = marks_stmt.where(SpecialEquipmentModel.mark_id.in_(rule_brand_ids))

    marks_stmt = marks_stmt.distinct().order_by(SpecialEquipmentMark.name.asc())
    product_marks = list((await session.execute(marks_stmt)).scalars().all())

    brand_name: str | None = None
    vehicle_marks: list[str] = []
    if product_marks:
        brand_name = ", ".join(product_marks)
        vehicle_marks = product_marks

    warehouse_access_type = await _compute_access_type(
        session,
        row.id,
        is_admin=is_admin,
        is_owner=is_owner,
        company_id=effective_company_id,
        owner_company_id=row.owner_company_id,
        actor_filter=actor_filter,
        actor_role=actor_role,
    )

    # Groups: list of group names from dealer_groups for active rules granted to actor's companies
    group_rules_stmt = (
        select(DealerGroup.name)
        .join(WarehouseAccessRule, WarehouseAccessRule.source_group_id == DealerGroup.id)
        .where(
            WarehouseAccessRule.warehouse_id == row.id,
            WarehouseAccessRule.is_active.is_(True),
            DealerGroup.is_active.is_(True),
        )
    )
    if actor_filter:
        group_rules_stmt = group_rules_stmt.where(
            WarehouseAccessRule.target_id.in_(actor_filter)
        )
    groups = list((await session.execute(group_rules_stmt.distinct())).scalars().all())

    # Sites: list of storefront names/slugs from catalog_storefronts for rules with site_id
    sites_stmt = (
        select(func.coalesce(Storefront.slug, "Основная витрина"))
        .join(WarehouseAccessRule, WarehouseAccessRule.site_id == Storefront.id)
        .where(
            WarehouseAccessRule.warehouse_id == row.id,
            WarehouseAccessRule.is_active.is_(True),
        )
    )
    if actor_filter and not is_admin and not is_owner:
        sites_stmt = sites_stmt.where(
            WarehouseAccessRule.target_id.in_(actor_filter)
        )
    sites = list((await session.execute(sites_stmt.distinct())).scalars().all())

    vehicles_count, vehicle_types = await _compute_vehicles_and_types(
        session,
        row,
        is_admin=is_admin,
        is_owner=is_owner,
        actor_filter=actor_filter,
        company_id=effective_company_id,
    )

    return _row_to_dict(
        row,
        city_name=city_name,
        owner_company_name=owner_company_name,
        brand_name=brand_name,
        selected_brands=selected_brands,
        category_name=category_name,
        warehouse_access_type=warehouse_access_type,
        groups=groups,
        vehicles_count=vehicles_count,
        vehicle_types=vehicle_types,
        sites=sites,
        vehicle_marks=vehicle_marks,
    )


@timed_repository
async def list_warehouses(
    session: AsyncSession,
    *,
    page: int = 1,
    limit: int = 20,
    search: str | None = None,
    brand_id: UUID | None = None,
    city_id: UUID | None = None,
    access_type: str | None = None,
    owner_company_id: UUID | None = None,
    is_active: bool | None = None,
    dealer_filter: list[UUID] | None = None,
    brand: str | None = None,
    status: WarehouseStatus | None = None,
    company_id: UUID | None = None,
    actor_role: str | None = None,
) -> tuple[list[dict[str, Any]], int]:
    conditions = _warehouse_scope_conditions(dealer_filter)
    if search:
        pattern = f"%{search}%"
        conditions.append(
            or_(
                Warehouse.name.ilike(pattern),
                Warehouse.address.ilike(pattern),
            )
        )
    if city_id is not None:
        conditions.append(Warehouse.city_id == city_id)
    if brand_id is not None:
        conditions.append(Warehouse.id.in_(_warehouses_for_actual_mark_ids([brand_id], dealer_filter=dealer_filter, company_id=company_id)))
    if owner_company_id is not None:
        conditions.append(Warehouse.owner_company_id == owner_company_id)
    if is_active is not None:
        conditions.append(Warehouse.is_active == is_active)
    elif status is not None:
        conditions.append(Warehouse.is_active == (status == WarehouseStatus.ACTIVE))

    if brand:
        conditions.append(
            or_(
                Warehouse.name.ilike(f"%{brand}%"),
                Warehouse.id.in_(_warehouses_for_actual_mark_ids(
                    select(SpecialEquipmentMark.id).where(SpecialEquipmentMark.name.ilike(f"%{brand}%")),
                    dealer_filter=dealer_filter, company_id=company_id,
                )),
            )
        )

    if access_type is not None:
        cond = _build_access_type_condition(
            dealer_filter,
            access_type,
            company_id=company_id,
            actor_role=actor_role,
        )
        if cond is not None:
            conditions.append(cond)

    where_clause = and_(*conditions) if conditions else None

    count_stmt = select(func.count(Warehouse.id))
    if where_clause is not None:
        count_stmt = count_stmt.where(where_clause)
    total = (await session.execute(count_stmt)).scalar() or 0

    list_stmt = select(Warehouse).order_by(Warehouse.created_at.desc(), Warehouse.id.desc())
    if where_clause is not None:
        list_stmt = list_stmt.where(where_clause)
    list_stmt = list_stmt.offset((page - 1) * limit).limit(limit)

    rows = (await session.execute(list_stmt)).scalars().all()
    items = [
        await _hydrate(
            session,
            r,
            actor_filter=dealer_filter,
            is_admin=(dealer_filter is None),
            company_id=company_id,
            actor_role=actor_role,
        )
        for r in rows
    ]
    return items, int(total)


@timed_repository
async def get_by_id(
    session: AsyncSession,
    warehouse_id: UUID,
    *,
    dealer_filter: list[UUID] | None = None,
    is_admin: bool | None = None,
    company_id: UUID | None = None,
    actor_role: str | None = None,
) -> dict[str, Any] | None:
    stmt = select(Warehouse).where(
        Warehouse.id == warehouse_id,
        *_warehouse_scope_conditions(dealer_filter),
    )
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        return None
    admin = is_admin if is_admin is not None else (dealer_filter is None)
    return await _hydrate(
        session,
        row,
        actor_filter=dealer_filter,
        is_admin=admin,
        company_id=company_id,
        actor_role=actor_role,
    )


@timed_repository
async def get_locked_by_id(
    session: AsyncSession, warehouse_id: UUID
) -> dict[str, Any] | None:
    """Lock a warehouse before assessing whether it can be deleted."""
    stmt = select(Warehouse).where(Warehouse.id == warehouse_id).with_for_update()
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        return None
    return {
        "id": row.id,
        "is_active": row.is_active,
        "status": "active" if row.is_active else "inactive",
        "company_id": row.owner_company_id,
        "owner_company_id": row.owner_company_id,
        "owner_company_type": row.owner_company_type,
    }


@timed_repository
async def get_delete_blocking_dependencies(
    session: AsyncSession, warehouse_id: UUID
) -> dict[str, int]:
    """Count dependency groups that prevent warehouse deletion."""
    exchange_links = union_all(
        select(ExchangeCartItemWarehouse.id).where(
            ExchangeCartItemWarehouse.warehouse_id == warehouse_id
        ),
        select(ExchangeRequestWarehouse.id).where(
            ExchangeRequestWarehouse.warehouse_id == warehouse_id
        ),
    ).subquery()
    stmt = select(
        select(func.count(SpecialEquipmentProduct.id))
        .where(
            SpecialEquipmentProduct.warehouse_id == warehouse_id,
            SpecialEquipmentProduct.publication_status != "archived",
        )
        .scalar_subquery()
        .label("special_equipment_links"),
        literal(0).label("vehicle_warehouses"),
        select(func.count(VehicleWarehouseTransfer.id))
        .where(
            or_(
                VehicleWarehouseTransfer.source_warehouse_id == warehouse_id,
                VehicleWarehouseTransfer.destination_warehouse_id == warehouse_id,
            )
        )
        .scalar_subquery()
        .label("transfer_history"),
        select(func.count())
        .select_from(exchange_links)
        .scalar_subquery()
        .label("exchange_links"),
        select(func.count(SpecialEquipmentImportJob.id))
        .where(SpecialEquipmentImportJob.target_warehouse_id == warehouse_id)
        .scalar_subquery()
        .label("import_jobs"),
        select(func.count(StorefrontWarehouse.storefront_id))
        .where(StorefrontWarehouse.warehouse_id == warehouse_id)
        .scalar_subquery()
        .label("storefronts"),
    )
    row = (await session.execute(stmt)).mappings().one()
    return {key: int(value) for key, value in row.items()}


@timed_repository
async def get_delete_blocking_dependencies_read_only(
    session: AsyncSession, warehouse_id: UUID
) -> dict[str, int]:
    """Read dependency counts in a fresh transaction that cannot write."""
    await session.execute(text("SET TRANSACTION READ ONLY"))
    return await get_delete_blocking_dependencies(session, warehouse_id)


def is_known_delete_dependency_integrity_error(exc: BaseException) -> bool:
    """Whether *exc* is a database backstop for warehouse dependencies only."""
    original = getattr(exc, "orig", exc)
    diagnostic = getattr(original, "diag", None)
    constraint_name = getattr(original, "constraint_name", None) or getattr(
        diagnostic, "constraint_name", None
    )
    return (
        getattr(original, "sqlstate", None) == "23503"
        and constraint_name
        in {
            "trg_warehouses_delete_blocked",
            "fk_se_products_warehouse",
            "fk_se_import_jobs_target_warehouse",
            "fk_vehicle_warehouse_transfers_source_warehouse_id",
            "fk_vehicle_warehouse_transfers_destination_warehouse_id",
            "vehicle_warehouse_transfers_source_warehouse_id_fkey",
            "vehicle_warehouse_transfers_destination_warehouse_id_fkey",
            "vehicle_warehouses_warehouse_id_fkey",
            "exchange_cart_item_warehouses_warehouse_id_fkey",
            "exchange_request_warehouses_warehouse_id_fkey",
            "catalog_storefront_warehouses_warehouse_id_fkey",
        }
    )


@timed_repository
async def create_warehouse(
    session: AsyncSession,
    *,
    name: str = "",
    owner_company_id: UUID | None = None,
    owner_company_type: str = "dealer",
    address: str,
    city_id: UUID | None = None,
    brand_ids: list[UUID] | None = None,
    category_id: UUID | None = None,
    is_active: bool = True,
    # Backward compatibility:
    brand: str | None = None,
    dealer_id: UUID | None = None,
    company_id: UUID | None = None,
) -> UUID:
    del brand
    eff_owner_company_id = owner_company_id or company_id or dealer_id
    if eff_owner_company_id is None:
        raise ValueError("owner_company_id is required to create a warehouse")
    eff_name = name.strip() or f"Склад {address}"

    row = Warehouse(
        name=eff_name,
        owner_company_id=eff_owner_company_id,
        owner_company_type=owner_company_type,
        address=address,
        city_id=city_id,
        category_id=category_id,
        is_active=is_active,
    )
    session.add(row)
    await session.flush()

    session.add_all([WarehouseMark(warehouse_id=row.id, mark_id=mark_id) for mark_id in brand_ids or []])

    # Automatically grant type 'A' rule to the owner company
    access_rule = WarehouseAccessRule(
        warehouse_id=row.id,
        target_type=owner_company_type,
        target_id=eff_owner_company_id,
        warehouse_access_type="A",
        is_visible=True,
        can_create_application=True,
        is_active=True,
    )
    session.add(access_rule)
    await session.flush()
    return row.id


@timed_repository
async def update_warehouse(
    session: AsyncSession,
    warehouse_id: UUID,
    *,
    name: str | None = None,
    address: str | None = None,
    city_id: UUID | None = None,
    brand_ids: list[UUID] | None = None,
    category_id: UUID | None = None,
    owner_company_id: UUID | None = None,
    owner_company_type: str | None = None,
    is_active: bool | None = None,
    update_city: bool = False,
    update_brands: bool = False,
    update_category: bool = False,
    update_owner_company: bool = False,
    # Backward compatibility:
    brand: str | None = None,
    dealer_id: UUID | None = None,
    company_id: UUID | None = None,
    status: WarehouseStatus | None = None,
    update_dealer: bool = False,
    update_company: bool = False,
) -> bool:
    del brand
    row = await session.get(Warehouse, warehouse_id)
    if row is None:
        return False
    if name is not None:
        row.name = name
    if address is not None:
        row.address = address
    if update_city:
        row.city_id = city_id
    if update_brands:
        await session.execute(sa.delete(WarehouseMark).where(WarehouseMark.warehouse_id == warehouse_id))
        session.add_all([WarehouseMark(warehouse_id=warehouse_id, mark_id=mark_id) for mark_id in brand_ids or []])
    if update_category:
        row.category_id = category_id
    if is_active is not None:
        row.is_active = is_active
    elif status is not None:
        row.is_active = (status == WarehouseStatus.ACTIVE)

    new_owner_id = (
        owner_company_id
        if update_owner_company
        else (company_id if update_company else (dealer_id if update_dealer else None))
    )
    if new_owner_id is not None and new_owner_id != row.owner_company_id:
        row.owner_company_id = new_owner_id
        if owner_company_type is not None:
            row.owner_company_type = owner_company_type

        # Reassign or recreate type 'A' rule for new owner
        a_rule_stmt = select(WarehouseAccessRule).where(
            WarehouseAccessRule.warehouse_id == warehouse_id,
            WarehouseAccessRule.warehouse_access_type == "A",
        )
        existing_a_rule = (await session.execute(a_rule_stmt)).scalar_one_or_none()
        if existing_a_rule is not None:
            existing_a_rule.target_id = new_owner_id
            existing_a_rule.target_type = row.owner_company_type
            existing_a_rule.is_active = True
            cast("Any", existing_a_rule).updated_at = datetime.now(UTC)
        else:
            new_a_rule = WarehouseAccessRule(
                warehouse_id=warehouse_id,
                target_type=row.owner_company_type,
                target_id=new_owner_id,
                warehouse_access_type="A",
                is_visible=True,
                can_create_application=True,
                is_active=True,
            )
            session.add(new_a_rule)

    cast("Any", row).updated_at = datetime.now(UTC)
    await session.flush()
    return True

@timed_repository
async def delete_warehouse(session: AsyncSession, warehouse_id: UUID) -> bool:
    row = await session.get(Warehouse, warehouse_id)
    if row is None:
        return False
    await session.execute(
        update(SpecialEquipmentProduct)
        .where(
            SpecialEquipmentProduct.warehouse_id == warehouse_id,
            SpecialEquipmentProduct.publication_status == "archived",
        )
        .values(warehouse_id=None)
    )
    await session.delete(row)
    await session.flush()
    return True

@timed_repository
async def city_exists(session: AsyncSession, city_id: UUID) -> bool:
    row = await session.get(City, city_id)
    return row is not None

@timed_repository
async def ensure_city(session: AsyncSession, city_id: UUID, name: str) -> None:
    """Insert a city with an explicit *city_id* when it does not yet exist.

    The warehouse import CSV may reference a city by a (deterministic) id whose
    row was never seeded into ``cities``. Creating the row here keeps the
    ``warehouses_city_id_fkey`` foreign key satisfied. Idempotent: an existing
    city is left untouched (its name is not overwritten)."""
    stmt = (
        pg_insert(City)
        .values(id=city_id, name=(name.strip() or "—"))
        .on_conflict_do_nothing(index_elements=[City.id])
    )
    await session.execute(stmt)


@timed_repository
async def resolve_or_create_city_by_name(
    session: AsyncSession, name: str
) -> UUID | None:
    """Return the id of the city matching *name* (case-insensitive), creating it
    if it does not yet exist. Returns ``None`` for an empty name."""
    clean = name.strip()
    if not clean:
        return None
    stmt = select(City.id).where(func.lower(City.name) == clean.lower()).limit(1)
    existing = (await session.execute(stmt)).scalar_one_or_none()
    if existing is not None:
        return existing
    row = City(name=clean)
    session.add(row)
    await session.flush()
    return row.id

@timed_repository
async def dealer_exists(session: AsyncSession, dealer_id: UUID) -> bool:
    stmt = select(Company.id).where(Company.id == dealer_id, Company.company_type == "dealer")
    result = await session.execute(stmt)
    return result.first() is not None

@timed_repository
async def company_exists(
    session: AsyncSession,
    company_id: UUID,
    *,
    allowed_types: tuple[str, ...] | None = None,
) -> bool:
    stmt = select(Company.id).where(Company.id == company_id)
    if allowed_types:
        stmt = stmt.where(Company.company_type.in_(allowed_types))
    result = await session.execute(stmt)
    return result.first() is not None


@timed_repository
async def dealer_company_exists(session: AsyncSession, company_id: UUID) -> bool:
    return await company_exists(session, company_id, allowed_types=("dealer",))

@timed_repository
async def list_users_by_company_id(
    session: AsyncSession, company_id: UUID
) -> list[dict[str, Any]]:
    stmt = (
        select(User.id, User.name, User.email, User.phone)
        .where(User.company_id == company_id, User.is_active.is_(True))
        .order_by(User.name)
    )
    result = await session.execute(stmt)
    return [
        {"id": r.id, "name": r.name, "email": r.email, "phone": r.phone}
        for r in result.all()
    ]

@timed_repository
async def get_first_active_dealer_by_company_id(
    session: AsyncSession, company_id: UUID
) -> UUID | None:
    # Phase 5: dealer_id references companies.id directly
    # If the company exists and is a dealer, return its own id
    stmt = select(Company.id).where(
        Company.id == company_id,
        Company.company_type == "dealer",
        Company.is_active.is_(True),
    ).limit(1)
    result = await session.execute(stmt)
    row = result.first()
    return row[0] if row else None


@timed_repository
async def resolve_actor_dealer_company_id(
    session: AsyncSession,
    user_id: UUID,
) -> UUID | None:
    """Resolve an actor's current company only when it is an active dealer."""
    stmt = (
        select(Company.id)
        .join(User, User.company_id == Company.id)
        .where(
            User.id == user_id,
            User.is_active.is_(True),
            Company.company_type == "dealer",
            Company.is_active.is_(True),
        )
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()

# ---------------------------------------------------------------------------
# Vehicle ↔ warehouse bindings
# ---------------------------------------------------------------------------

@timed_repository
async def list_warehouse_vehicles(
    session: AsyncSession,
    warehouse_id: UUID,
    *,
    page: int = 1,
    limit: int = 20,
    status: str | None = None,
) -> tuple[list[dict[str, Any]], int]:
    conditions: list[Any] = [SpecialEquipmentProduct.warehouse_id == warehouse_id]
    if status is not None:
        conditions.append(SpecialEquipmentProduct.sale_status == status)
    count_stmt = select(func.count(SpecialEquipmentProduct.id)).where(*conditions)
    total = (await session.execute(count_stmt)).scalar() or 0

    stmt = (
        select(
            SpecialEquipmentProduct.id,
            SpecialEquipmentProduct.vin,
            SpecialEquipmentModel.mark_id,
            SpecialEquipmentMark.name.label("mark_name"),
            SpecialEquipmentModification.model_id,
            SpecialEquipmentModel.name.label("model_name"),
            SpecialEquipmentProduct.manufacture_year.label("year"),
            SpecialEquipmentProduct.price.label("base_price"),
            SpecialEquipmentProduct.special_price.label("discount_price"),
            sql_cast(None, String).label("color"),
            SpecialEquipmentProduct.sale_status.label("status"),
            SpecialEquipmentProduct.updated_at.label("bound_at"),
        )
        .select_from(SpecialEquipmentProduct)
        .outerjoin(
            SpecialEquipmentModification,
            SpecialEquipmentModification.id == SpecialEquipmentProduct.modification_id,
        )
        .outerjoin(
            SpecialEquipmentModel,
            SpecialEquipmentModel.id
            == sa.func.coalesce(
                SpecialEquipmentModification.model_id,
                SpecialEquipmentProduct.model_id,
            ),
        )
        .outerjoin(
            SpecialEquipmentMark,
            SpecialEquipmentMark.id == SpecialEquipmentModel.mark_id,
        )
        .where(*conditions)
        .order_by(SpecialEquipmentProduct.updated_at.desc(), SpecialEquipmentProduct.id.desc())
        .offset((page - 1) * limit)
        .limit(limit)
    )
    result = await session.execute(stmt)
    items = [
        {
            "id": r.id,
            "vin": r.vin,
            "mark_id": r.mark_id,
            "mark_name": r.mark_name,
            "model_id": r.model_id,
            "model_name": r.model_name,
            "year": r.year,
            "base_price": r.base_price,
            "discount_price": r.discount_price,
            "color": r.color,
            "status": r.status,
            "bound_at": r.bound_at,
        }
        for r in result.all()
    ]
    await enrich_stock_status(session, items)
    return items, int(total)


@timed_repository
async def get_binding(
    session: AsyncSession, vehicle_id: UUID
) -> dict[str, Any] | None:
    row = await session.get(SpecialEquipmentProduct, vehicle_id)
    if row is None or row.warehouse_id is None:
        return None
    return {
        "id": row.id,
        "product_id": row.id,
        "vehicle_id": row.id,
        "warehouse_id": row.warehouse_id,
    }


@timed_repository
async def get_product_warehouse_owner_type(
    session: AsyncSession, product_id: UUID
) -> str | None:
    """Read the actual warehouse owner; seller/actor are not source fallbacks."""
    statement = (
        select(Company.company_type)
        .select_from(SpecialEquipmentProduct)
        .join(Warehouse, Warehouse.id == SpecialEquipmentProduct.warehouse_id)
        .join(Company, Company.id == Warehouse.owner_company_id)
        .where(SpecialEquipmentProduct.id == product_id)
    )
    return (await session.execute(statement)).scalar_one_or_none()


@timed_repository
async def resolve_dealer_company_id(
    session: AsyncSession, vehicle_id: UUID
) -> UUID | None:
    """Return an active dealer company that owns the vehicle's warehouse."""
    stmt = (
        select(
            Warehouse.owner_company_id,
            Company.company_type,
            Company.is_active,
            SpecialEquipmentProduct.seller_company_id,
        )
        .select_from(SpecialEquipmentProduct)
        .outerjoin(Warehouse, Warehouse.id == SpecialEquipmentProduct.warehouse_id)
        .outerjoin(Company, Company.id == Warehouse.owner_company_id)
        .where(SpecialEquipmentProduct.id == vehicle_id)
        .limit(1)
    )
    warehouse_owner = (await session.execute(stmt)).first()
    if warehouse_owner is not None:
        if (
            warehouse_owner.owner_company_id is not None
            and warehouse_owner.company_type == "dealer"
            and warehouse_owner.is_active is True
        ):
            return warehouse_owner.owner_company_id
        if warehouse_owner.owner_company_id is not None:
            return None
        if warehouse_owner.seller_company_id is not None:
            seller = await session.get(Company, warehouse_owner.seller_company_id)
            if seller and seller.company_type == "dealer" and seller.is_active:
                return seller.id
    return None


@timed_repository
async def resolve_application_dealer_company_id(
    session: AsyncSession,
    vehicle_ids: list[UUID],
) -> UUID | None:
    """Resolve the application dealer without making the result order-sensitive."""
    if not vehicle_ids:
        return None

    warehouse_company = aliased(Company)
    seller_company = aliased(Company)
    stmt = (
        select(
            SpecialEquipmentProduct.id.label("product_id"),
            SpecialEquipmentProduct.warehouse_id.label("warehouse_id"),
            warehouse_company.id.label("warehouse_company_id"),
            warehouse_company.company_type.label("warehouse_company_type"),
            warehouse_company.is_active.label("warehouse_company_is_active"),
            seller_company.id.label("seller_company_id"),
            seller_company.company_type.label("seller_company_type"),
            seller_company.is_active.label("seller_company_is_active"),
        )
        .select_from(SpecialEquipmentProduct)
        .outerjoin(Warehouse, Warehouse.id == SpecialEquipmentProduct.warehouse_id)
        .outerjoin(warehouse_company, warehouse_company.id == Warehouse.owner_company_id)
        .outerjoin(seller_company, seller_company.id == SpecialEquipmentProduct.seller_company_id)
        .where(SpecialEquipmentProduct.id.in_(vehicle_ids))
    )
    rows = {
        row.product_id: row
        for row in (await session.execute(stmt)).all()
    }
    resolved_dealers: list[UUID] = []
    for vehicle_id in vehicle_ids:
        row = rows.get(vehicle_id)
        if row is None:
            continue
        if row.warehouse_id is not None:
            if (
                row.warehouse_company_id is None
                or row.warehouse_company_type != "dealer"
                or row.warehouse_company_is_active is not True
            ):
                return None
            resolved_dealers.append(row.warehouse_company_id)
            continue
        if (
            row.seller_company_id is not None
            and row.seller_company_type == "dealer"
            and row.seller_company_is_active is True
        ):
            resolved_dealers.append(row.seller_company_id)

    unique_dealers = set(resolved_dealers)
    if len(unique_dealers) == 1:
        return next(iter(unique_dealers))
    return None


@timed_repository
async def vehicle_exists(session: AsyncSession, vehicle_id: UUID) -> bool:
    row = await session.get(SpecialEquipmentProduct, vehicle_id)
    return row is not None


@timed_repository
async def get_existing_vehicle_ids(
    session: AsyncSession, vehicle_ids: list[UUID]
) -> set[UUID]:
    if not vehicle_ids:
        return set()
    result = await session.execute(
        select(SpecialEquipmentProduct.id).where(SpecialEquipmentProduct.id.in_(vehicle_ids))
    )
    return set(result.scalars())


@timed_repository
async def bulk_create_unbound_bindings(
    session: AsyncSession, *, warehouse_id: UUID, vehicle_ids: list[UUID]
) -> int:
    if not vehicle_ids:
        return 0
    stmt = (
        update(SpecialEquipmentProduct)
        .where(
            SpecialEquipmentProduct.id.in_(vehicle_ids),
            SpecialEquipmentProduct.warehouse_id.is_(None),
        )
        .values(warehouse_id=warehouse_id)
    )
    result = await session.execute(stmt)
    await session.flush()
    return cast("CursorResult[Any]", result).rowcount or 0


@timed_repository
async def create_binding(
    session: AsyncSession, *, vehicle_id: UUID, warehouse_id: UUID
) -> bool:
    """Bind a vehicle to a warehouse."""
    prod = await session.get(SpecialEquipmentProduct, vehicle_id)
    if prod is None:
        return False
    wh = await session.get(Warehouse, warehouse_id)
    if wh is None:
        raise WarehouseBindingTargetUnavailableError
    prod.warehouse_id = warehouse_id
    await session.flush()
    return True


@timed_repository
async def delete_binding(
    session: AsyncSession, *, warehouse_id: UUID, vehicle_id: UUID
) -> bool:
    from infrastructure.models.applications import ApplicationVehicleAllocation

    claimed = (
        await session.execute(
            select(ApplicationVehicleAllocation.id).where(
                ApplicationVehicleAllocation.product_id == vehicle_id,
                ApplicationVehicleAllocation.released_at.is_(None),
            ).limit(1)
        )
    ).scalar_one_or_none()
    if claimed:
        from domain.errors import ApplicationVehicleAssignmentError
        raise ApplicationVehicleAssignmentError("Нельзя отвязать автомобиль, закреплённый за заявкой или завершённой сделкой")

    prod = await session.get(SpecialEquipmentProduct, vehicle_id)
    if prod is None or prod.warehouse_id != warehouse_id:
        return False
    prod.warehouse_id = None
    await session.flush()
    return True


@timed_repository
async def mark_exists(session: AsyncSession, mark_id: Any) -> bool:
    try:
        uid = UUID(str(mark_id))
    except (ValueError, TypeError):
        return False
    row = await session.get(SpecialEquipmentMark, uid)
    return row is not None


@timed_repository
async def find_mark_id_by_name(session: AsyncSession, name: str) -> UUID | None:
    stmt = select(SpecialEquipmentMark.id).where(SpecialEquipmentMark.name.ilike(name.strip()))
    return (await session.execute(stmt)).scalar_one_or_none()



@timed_repository
async def list_unbound_vehicle_ids_by_mark(
    session: AsyncSession, mark_id: Any
) -> list[UUID]:
    """All vehicles of a given mark that are NOT yet bound to any warehouse."""
    try:
        uid = UUID(str(mark_id))
    except (ValueError, TypeError):
        return []
    stmt = (
        select(SpecialEquipmentProduct.id)
        .select_from(SpecialEquipmentProduct)
        .outerjoin(
            SpecialEquipmentModification,
            SpecialEquipmentModification.id == SpecialEquipmentProduct.modification_id,
        )
        .join(
            SpecialEquipmentModel,
            SpecialEquipmentModel.id
            == sa.func.coalesce(
                SpecialEquipmentModification.model_id,
                SpecialEquipmentProduct.model_id,
            ),
        )
        .where(
            SpecialEquipmentModel.mark_id == uid,
            SpecialEquipmentProduct.warehouse_id.is_(None),
        )
        .order_by(SpecialEquipmentProduct.id)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


@timed_repository
async def bulk_create_bindings(
    session: AsyncSession,
    warehouse_id: UUID,
    vehicle_ids: list[UUID],
) -> int:
    if not vehicle_ids:
        return 0
    stmt = (
        update(SpecialEquipmentProduct)
        .where(SpecialEquipmentProduct.id.in_(vehicle_ids))
        .values(warehouse_id=warehouse_id)
    )
    result = await session.execute(stmt)
    await session.flush()
    return cast("CursorResult[Any]", result).rowcount or 0


@timed_repository
async def list_available_warehouses(
    session: AsyncSession,
    *,
    dealer_filter: list[UUID] | None,
) -> list[dict[str, Any]]:
    """List warehouses accessible to an employee or distributor scope."""
    if dealer_filter == []:
        return []

    stmt = (
        select(
            Warehouse.id,
            Warehouse.name,
            Warehouse.address,
            Warehouse.city_id,
            City.name.label("city_name"),
            Warehouse.owner_company_id,
            Warehouse.owner_company_type,
            func.count(SpecialEquipmentProduct.id).label("vehicles_count"),
        )
        .outerjoin(City, City.id == Warehouse.city_id)
        .outerjoin(
            SpecialEquipmentProduct,
            SpecialEquipmentProduct.warehouse_id == Warehouse.id,
        )
        .group_by(
            Warehouse.id,
            Warehouse.name,
            Warehouse.address,
            Warehouse.city_id,
            City.name,
            Warehouse.owner_company_id,
            Warehouse.owner_company_type,
        )
        .order_by(Warehouse.address, Warehouse.name, Warehouse.id)
    )
    if dealer_filter is not None:
        stmt = stmt.where(
            or_(
                Warehouse.owner_company_id.in_(dealer_filter),
                Warehouse.id.in_(
                    select(WarehouseAccessRule.warehouse_id).where(
                        WarehouseAccessRule.target_id.in_(dealer_filter),
                        WarehouseAccessRule.is_active.is_(True),
                    )
                ),
            )
        )
    result = await session.execute(stmt)
    rows = result.all()
    brands = {row.id: await get_selected_brands(session, row.id) for row in rows}
    return [
        {
            "id": row.id,
            "name": row.name,
            "address": row.address,
            "brand_ids": [brand["id"] for brand in brands[row.id]],
            "selected_brands": brands[row.id],
            "brand": ", ".join(brand["name"] for brand in brands[row.id]),
            "city_id": row.city_id,
            "city_name": row.city_name,
            "owner_company_id": row.owner_company_id,
            "owner_company_type": row.owner_company_type,
            "dealer_id": row.owner_company_id,
            "company_id": row.owner_company_id,
            "vehicles_count": int(row.vehicles_count),
        }
        for row in rows
    ]


def _source_vehicle_conditions(
    *,
    source_warehouse_id: UUID,
    dealer_filter: list[UUID] | None,
    vin: str | None = None,
    mark_ids: list[Any] | None = None,
    model_ids: list[Any] | None = None,
    years: list[int] | None = None,
    colors: list[str] | None = None,
) -> list[Any]:
    del colors
    conditions: list[Any] = [SpecialEquipmentProduct.warehouse_id == source_warehouse_id]
    if dealer_filter == []:
        conditions.append(false())
    elif dealer_filter is not None:
        conditions.append(SpecialEquipmentProduct.seller_company_id.in_(dealer_filter))
    if vin:
        conditions.append(SpecialEquipmentProduct.vin.ilike(f"%{vin}%"))
    if mark_ids:
        m_uids = []
        for m in mark_ids:
            with contextlib.suppress(ValueError, TypeError):
                m_uids.append(UUID(str(m)))
        if m_uids:
            conditions.append(SpecialEquipmentModel.mark_id.in_(m_uids))
    if model_ids:
        mo_uids = []
        for mo in model_ids:
            with contextlib.suppress(ValueError, TypeError):
                mo_uids.append(UUID(str(mo)))
        if mo_uids:
            conditions.append(SpecialEquipmentModification.model_id.in_(mo_uids))
    if years:
        conditions.append(SpecialEquipmentProduct.manufacture_year.in_(years))
    return conditions


@timed_repository
async def list_source_warehouse_vehicles(
    session: AsyncSession,
    *,
    source_warehouse_id: UUID,
    dealer_filter: list[UUID] | None,
    page: int = 1,
    limit: int = 20,
    vin: str | None = None,
    mark_ids: list[Any] | None = None,
    model_ids: list[Any] | None = None,
    years: list[int] | None = None,
    colors: list[str] | None = None,
) -> tuple[list[dict[str, Any]], int, dict[str, list[Any]]]:
    """List current source-warehouse vehicles inside a resolved dealer scope."""
    conditions = _source_vehicle_conditions(
        source_warehouse_id=source_warehouse_id,
        dealer_filter=dealer_filter,
        vin=vin,
        mark_ids=mark_ids,
        model_ids=model_ids,
        years=years,
        colors=colors,
    )
    count_stmt = (
        select(func.count(SpecialEquipmentProduct.id))
        .select_from(SpecialEquipmentProduct)
        .outerjoin(
            SpecialEquipmentModification,
            SpecialEquipmentModification.id == SpecialEquipmentProduct.modification_id,
        )
        .outerjoin(
            SpecialEquipmentModel,
            SpecialEquipmentModel.id
            == sa.func.coalesce(
                SpecialEquipmentModification.model_id,
                SpecialEquipmentProduct.model_id,
            ),
        )
        .where(*conditions)
    )
    total = int((await session.execute(count_stmt)).scalar() or 0)

    stmt = (
        select(
            SpecialEquipmentProduct.id,
            SpecialEquipmentProduct.vin,
            SpecialEquipmentModel.mark_id,
            SpecialEquipmentMark.name.label("mark_name"),
            sa.func.coalesce(
                SpecialEquipmentModification.model_id,
                SpecialEquipmentProduct.model_id,
            ).label("model_id"),
            SpecialEquipmentModel.name.label("model_name"),
            SpecialEquipmentProduct.manufacture_year.label("year"),
            sql_cast(None, String).label("color"),
            SpecialEquipmentProduct.warehouse_id.label("source_warehouse_id"),
        )
        .select_from(SpecialEquipmentProduct)
        .outerjoin(
            SpecialEquipmentModification,
            SpecialEquipmentModification.id == SpecialEquipmentProduct.modification_id,
        )
        .outerjoin(
            SpecialEquipmentModel,
            SpecialEquipmentModel.id
            == sa.func.coalesce(
                SpecialEquipmentModification.model_id,
                SpecialEquipmentProduct.model_id,
            ),
        )
        .outerjoin(
            SpecialEquipmentMark,
            SpecialEquipmentMark.id == SpecialEquipmentModel.mark_id,
        )
        .where(*conditions)
        .order_by(SpecialEquipmentProduct.updated_at.desc(), SpecialEquipmentProduct.id.desc())
        .offset((page - 1) * limit)
        .limit(limit)
    )
    result = await session.execute(stmt)
    marks_result = await session.execute(
        select(SpecialEquipmentMark.id, SpecialEquipmentMark.name)
        .select_from(SpecialEquipmentProduct)
        .outerjoin(
            SpecialEquipmentModification,
            SpecialEquipmentModification.id == SpecialEquipmentProduct.modification_id,
        )
        .join(
            SpecialEquipmentModel,
            SpecialEquipmentModel.id
            == sa.func.coalesce(
                SpecialEquipmentModification.model_id,
                SpecialEquipmentProduct.model_id,
            ),
        )
        .join(
            SpecialEquipmentMark,
            SpecialEquipmentMark.id == SpecialEquipmentModel.mark_id,
        )
        .where(*conditions)
        .group_by(SpecialEquipmentMark.id, SpecialEquipmentMark.name)
        .order_by(SpecialEquipmentMark.name, SpecialEquipmentMark.id)
    )
    models_result = await session.execute(
        select(SpecialEquipmentModel.id, SpecialEquipmentModel.name, SpecialEquipmentModel.mark_id)
        .select_from(SpecialEquipmentProduct)
        .outerjoin(
            SpecialEquipmentModification,
            SpecialEquipmentModification.id == SpecialEquipmentProduct.modification_id,
        )
        .join(
            SpecialEquipmentModel,
            SpecialEquipmentModel.id
            == sa.func.coalesce(
                SpecialEquipmentModification.model_id,
                SpecialEquipmentProduct.model_id,
            ),
        )
        .where(*conditions)
        .group_by(SpecialEquipmentModel.id, SpecialEquipmentModel.name, SpecialEquipmentModel.mark_id)
        .order_by(SpecialEquipmentModel.name, SpecialEquipmentModel.id)
    )
    years_result = await session.execute(
        select(SpecialEquipmentProduct.manufacture_year.label("year"))
        .select_from(SpecialEquipmentProduct)
        .outerjoin(
            SpecialEquipmentModification,
            SpecialEquipmentModification.id == SpecialEquipmentProduct.modification_id,
        )
        .outerjoin(
            SpecialEquipmentModel,
            SpecialEquipmentModel.id
            == sa.func.coalesce(
                SpecialEquipmentModification.model_id,
                SpecialEquipmentProduct.model_id,
            ),
        )
        .where(*conditions, SpecialEquipmentProduct.manufacture_year.is_not(None))
        .group_by(SpecialEquipmentProduct.manufacture_year)
        .order_by(SpecialEquipmentProduct.manufacture_year.desc())
    )
    facets: dict[str, list[Any]] = {
        "marks": [{"id": row.id, "name": row.name} for row in marks_result.all()],
        "models": [
            {"id": row.id, "name": row.name, "mark_id": row.mark_id}
            for row in models_result.all()
        ],
        "years": [row.year for row in years_result.all()],
        "colors": [],
    }
    return (
        [
            {
                "id": row.id,
                "vin": row.vin,
                "mark_id": row.mark_id,
                "mark_name": row.mark_name,
                "model_id": row.model_id,
                "model_name": row.model_name,
                "year": row.year,
                "color": row.color,
                "source_warehouse_id": row.source_warehouse_id,
            }
            for row in result.all()
        ],
        total,
        facets,
    )


@timed_repository
async def list_source_warehouse_vehicle_ids(
    session: AsyncSession,
    *,
    source_warehouse_id: UUID,
    dealer_filter: list[UUID] | None,
) -> list[UUID]:
    """Return the current scoped candidate IDs for all-filtered transfer."""
    conditions = _source_vehicle_conditions(
        source_warehouse_id=source_warehouse_id,
        dealer_filter=dealer_filter,
    )
    result = await session.execute(
        select(SpecialEquipmentProduct.id)
        .select_from(SpecialEquipmentProduct)
        .outerjoin(
            SpecialEquipmentModification,
            SpecialEquipmentModification.id == SpecialEquipmentProduct.modification_id,
        )
        .outerjoin(
            SpecialEquipmentModel,
            SpecialEquipmentModel.id
            == sa.func.coalesce(
                SpecialEquipmentModification.model_id,
                SpecialEquipmentProduct.model_id,
            ),
        )
        .where(*conditions)
        .order_by(SpecialEquipmentProduct.id)
    )
    return list(result.scalars())


@timed_repository
async def transfer_vehicle_if_current(
    session: AsyncSession,
    *,
    vehicle_id: UUID,
    source_warehouse_id: UUID,
    destination_warehouse_id: UUID,
    actor_user_id: UUID | None,
) -> bool:
    """Atomically move a current binding and append its audit record."""
    result = await session.execute(
        update(SpecialEquipmentProduct)
        .where(
            SpecialEquipmentProduct.id == vehicle_id,
            SpecialEquipmentProduct.warehouse_id == source_warehouse_id,
        )
        .values(warehouse_id=destination_warehouse_id)
    )
    if cast("CursorResult[Any]", result).rowcount != 1:
        return False

    product = (
        await session.execute(
            select(
                SpecialEquipmentProduct.id,
                SpecialEquipmentProduct.vin,
                SpecialEquipmentProduct.code,
            ).where(SpecialEquipmentProduct.id == vehicle_id)
        )
    ).one_or_none()

    warehouses = (
        await session.execute(
            select(
                Warehouse.id,
                Warehouse.name,
                Warehouse.address,
                Warehouse.owner_company_id,
            ).where(Warehouse.id.in_([source_warehouse_id, destination_warehouse_id]))
        )
    ).all()
    wh_map = {row.id: row for row in warehouses}
    source_wh = wh_map.get(source_warehouse_id)
    dest_wh = wh_map.get(destination_warehouse_id)

    product_snapshot: dict[str, Any] = {
        "id": str(vehicle_id),
        "vin": product.vin if product else None,
        "code": product.code if product else None,
        "title": (product.code or "") if product else "",
    }
    source_snapshot: dict[str, Any] = {
        "id": str(source_warehouse_id),
        "name": source_wh.name if source_wh else "",
        "address": source_wh.address if source_wh else "",
        "owner_company_id": str(source_wh.owner_company_id) if source_wh else None,
    }
    dest_snapshot: dict[str, Any] = {
        "id": str(destination_warehouse_id),
        "name": dest_wh.name if dest_wh else "",
        "address": dest_wh.address if dest_wh else "",
        "owner_company_id": str(dest_wh.owner_company_id) if dest_wh else None,
    }

    session.add(
        VehicleWarehouseTransfer(
            product_id=vehicle_id,
            source_warehouse_id=source_warehouse_id,
            destination_warehouse_id=destination_warehouse_id,
            actor_user_id=actor_user_id,
            product_snapshot=product_snapshot,
            source_warehouse_snapshot=source_snapshot,
            destination_warehouse_snapshot=dest_snapshot,
        )
    )
    await session.flush()
    return True


# ---------------------------------------------------------------------------
# Misc helpers — kept for compatibility with future integrations.
# ---------------------------------------------------------------------------

@timed_repository
async def list_warehouse_brands(
    session: AsyncSession,
    *,
    dealer_filter: list[UUID] | None = None,
) -> list[str]:
    del dealer_filter
    stmt = (
        select(SpecialEquipmentMark.name)
        .where(SpecialEquipmentMark.name.is_not(None))
        .distinct()
        .order_by(SpecialEquipmentMark.name)
    )
    result = await session.execute(stmt)
    return [row[0] for row in result.all() if row[0]]


@timed_repository
async def search_warehouses_by_address_or_brand(
    session: AsyncSession, query: str
) -> list[dict[str, Any]]:
    pattern = f"%{query}%"
    stmt = (
        select(Warehouse)
        .outerjoin(WarehouseMark, WarehouseMark.warehouse_id == Warehouse.id)
        .outerjoin(SpecialEquipmentMark, SpecialEquipmentMark.id == WarehouseMark.mark_id)
        .where(
            or_(
                Warehouse.name.ilike(pattern),
                Warehouse.address.ilike(pattern),
                SpecialEquipmentMark.name.ilike(pattern),
            )
        )
    )
    rows = (await session.execute(stmt)).scalars().unique().all()
    return [await _hydrate(session, r, is_admin=True) for r in rows]


@timed_repository
async def has_showcase_only_access(
    session: AsyncSession,
    *,
    company_id: UUID,
    vehicle_ids: list[UUID],
) -> bool:
    """Check if any vehicle belongs to a warehouse where company only has Type C access."""
    if not vehicle_ids:
        return False
    prods_stmt = (
        select(SpecialEquipmentProduct.warehouse_id, Warehouse.owner_company_id)
        .join(Warehouse, Warehouse.id == SpecialEquipmentProduct.warehouse_id)
        .where(
            SpecialEquipmentProduct.id.in_(vehicle_ids),
            SpecialEquipmentProduct.warehouse_id.is_not(None),
        )
    )
    wh_rows = (await session.execute(prods_stmt)).all()
    for wh_id, owner_id in wh_rows:
        if wh_id is None or owner_id == company_id:
            continue
        rules_stmt = select(WarehouseAccessRule).where(
            WarehouseAccessRule.warehouse_id == wh_id,
            WarehouseAccessRule.target_id == company_id,
            WarehouseAccessRule.is_active.is_(True),
        )
        rules = (await session.execute(rules_stmt)).scalars().all()
        if rules and not any(r.can_create_application for r in rules):
            return True
    return False



async def get_selected_brands(session: AsyncSession, warehouse_id: UUID) -> list[dict[str, Any]]:
    rows = await session.execute(
        select(SpecialEquipmentMark.id, SpecialEquipmentMark.name)
        .join(WarehouseMark, WarehouseMark.mark_id == SpecialEquipmentMark.id)
        .where(WarehouseMark.warehouse_id == warehouse_id)
        .order_by(SpecialEquipmentMark.name, SpecialEquipmentMark.id)
    )
    return [dict(row._mapping) for row in rows]


def _warehouses_for_actual_mark_ids(
    mark_ids: Any, *, dealer_filter: list[UUID] | None, company_id: UUID | None,
) -> Any:
    stmt = (
        select(SpecialEquipmentProduct.warehouse_id)
        .outerjoin(SpecialEquipmentModification, SpecialEquipmentModification.id == SpecialEquipmentProduct.modification_id)
        .join(SpecialEquipmentModel, SpecialEquipmentModel.id == func.coalesce(SpecialEquipmentModification.model_id, SpecialEquipmentProduct.model_id))
        .where(SpecialEquipmentModel.mark_id.in_(mark_ids))
    )
    if dealer_filter is None:
        return stmt
    effective_company_id = company_id
    if effective_company_id is None and len(dealer_filter) == 1:
        effective_company_id = dealer_filter[0]
    scope_warehouse = aliased(Warehouse)
    stmt = stmt.join(scope_warehouse, scope_warehouse.id == SpecialEquipmentProduct.warehouse_id)
    target_ids = [effective_company_id] if effective_company_id is not None else dealer_filter
    rule_conditions = [
        WarehouseAccessRule.warehouse_id == SpecialEquipmentProduct.warehouse_id,
        WarehouseAccessRule.is_active.is_(True),
        WarehouseAccessRule.target_id.in_(target_ids),
    ]
    # Mirrors _hydrate: owners see all stock; other actors see available published
    # products, constrained by their active rules when every rule limits a mark.
    allowed_by_rules = or_(
        ~select(WarehouseAccessRule.id).where(*rule_conditions).exists(),
        select(WarehouseAccessRule.id).where(
            *rule_conditions,
            or_(WarehouseAccessRule.brand_id.is_(None), WarehouseAccessRule.brand_id == SpecialEquipmentModel.mark_id),
        ).exists(),
    )
    return stmt.where(or_(
        scope_warehouse.owner_company_id == effective_company_id if effective_company_id is not None else false(),
        and_(
            SpecialEquipmentProduct.publication_status == "published",
            SpecialEquipmentProduct.sale_status == "available",
            allowed_by_rules,
        ),
    ))


def _category_ids_for_marks(brand_ids: list[UUID]) -> Any:
    model_categories = (
        select(SpecialEquipmentModel.category_id.label("category_id"))
        .join(SpecialEquipmentMark, SpecialEquipmentMark.id == SpecialEquipmentModel.mark_id)
        .where(
            SpecialEquipmentModel.mark_id.in_(brand_ids),
            SpecialEquipmentModel.is_active.is_(True),
            SpecialEquipmentMark.is_active.is_(True),
            SpecialEquipmentModel.category_id.is_not(None),
        )
    )
    modification_categories = (
        select(SpecialEquipmentModificationCategory.category_id)
        .join(SpecialEquipmentModification, SpecialEquipmentModification.id == SpecialEquipmentModificationCategory.modification_id)
        .join(SpecialEquipmentModel, SpecialEquipmentModel.id == SpecialEquipmentModification.model_id)
        .join(SpecialEquipmentMark, SpecialEquipmentMark.id == SpecialEquipmentModel.mark_id)
        .where(
            SpecialEquipmentModel.mark_id.in_(brand_ids),
            SpecialEquipmentModel.is_active.is_(True),
            SpecialEquipmentModification.is_active.is_(True),
            SpecialEquipmentMark.is_active.is_(True),
        )
    )
    return model_categories.union(modification_categories)


async def active_mark_ids(session: AsyncSession, brand_ids: list[UUID]) -> set[UUID]:
    if not brand_ids:
        return set()
    return set((await session.execute(
        select(SpecialEquipmentMark.id).where(SpecialEquipmentMark.id.in_(brand_ids), SpecialEquipmentMark.is_active.is_(True))
    )).scalars().all())


async def category_available_for_marks(session: AsyncSession, category_id: UUID, brand_ids: list[UUID]) -> bool:
    if not brand_ids:
        return False
    return (await session.scalar(
        select(SpecialEquipmentCategory.id).where(
            SpecialEquipmentCategory.id == category_id,
            SpecialEquipmentCategory.is_active.is_(True),
            SpecialEquipmentCategory.id.in_(_category_ids_for_marks(brand_ids)),
        )
    )) is not None


async def list_form_marks(session: AsyncSession, *, search: str | None, page: int, limit: int) -> tuple[list[dict[str, Any]], int]:
    conditions = [SpecialEquipmentMark.is_active.is_(True)]
    if search and search.strip():
        conditions.append(SpecialEquipmentMark.name.ilike(f"%{search.strip()}%"))
    total = int(await session.scalar(select(func.count()).select_from(SpecialEquipmentMark).where(*conditions)) or 0)
    rows = await session.execute(
        select(SpecialEquipmentMark.id, SpecialEquipmentMark.name).where(*conditions)
        .order_by(SpecialEquipmentMark.name, SpecialEquipmentMark.id).offset((page - 1) * limit).limit(limit)
    )
    return [dict(row._mapping) for row in rows], total


async def list_form_categories(session: AsyncSession, *, brand_ids: list[UUID], search: str | None, page: int, limit: int) -> tuple[list[dict[str, Any]], int]:
    if not brand_ids:
        return [], 0
    conditions = [SpecialEquipmentCategory.is_active.is_(True), SpecialEquipmentCategory.id.in_(_category_ids_for_marks(brand_ids))]
    if search and search.strip():
        conditions.append(SpecialEquipmentCategory.name.ilike(f"%{search.strip()}%"))
    total = int(await session.scalar(select(func.count()).select_from(SpecialEquipmentCategory).where(*conditions)) or 0)
    rows = await session.execute(
        select(SpecialEquipmentCategory.id, SpecialEquipmentCategory.name).where(*conditions)
        .order_by(SpecialEquipmentCategory.name, SpecialEquipmentCategory.id).offset((page - 1) * limit).limit(limit)
    )
    return [dict(row._mapping) for row in rows], total


async def lock_warehouse_for_update(session: AsyncSession, warehouse_id: UUID) -> None:
    await session.execute(select(Warehouse.id).where(Warehouse.id == warehouse_id).with_for_update())
