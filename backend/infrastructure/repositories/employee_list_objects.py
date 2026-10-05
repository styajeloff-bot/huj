"""Batch effective employee object sets before filtering and pagination."""

from __future__ import annotations

from collections import defaultdict
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.models.companies import Company, DistributorBrand
from infrastructure.models.special_equipment import (
    SpecialEquipmentMark,
    SpecialEquipmentModel,
    SpecialEquipmentModification,
    SpecialEquipmentProduct,
)
from infrastructure.models.support import DealerGroup, DealerGroupMember
from infrastructure.models.user_company_access import UserCompanyAccessRule
from infrastructure.models.vehicles import (
    City,
    Warehouse,
    WarehouseAccessRule,
    WarehouseMark,
)
from infrastructure.repositories.user_company_access_repository import (
    PersonalAccessRules,
    _apply_rule_to_personal_access,
)


def _restrict(base: set[UUID], mode: str | None, selected: set[UUID]) -> set[UUID]:
    if mode == "none":
        return set()
    if mode == "selected":
        return base & selected
    if mode == "except_selected":
        return base - selected
    return base


def _objects(ids: set[UUID], names: dict[UUID, str]) -> list[dict[str, str]]:
    return [
        {"id": str(key), "name": names[key]}
        for key in sorted(ids & names.keys(), key=lambda key: (names[key], str(key)))
    ]


async def hydrate_employee_objects(  # noqa: PLR0912
    session: AsyncSession, items: list[dict[str, Any]]
) -> None:
    """Load each relation once and intersect personal selections with company rights."""
    if not items:
        return
    company_ids = {UUID(item["company_id"]) for item in items}
    link_ids = {UUID(item["user_company_id"]) for item in items}
    brands: dict[UUID, set[UUID]] = defaultdict(set)
    own: dict[UUID, set[UUID]] = defaultdict(set)
    distributors: dict[UUID, set[UUID]] = defaultdict(set)
    distributor_names: dict[UUID, str] = {}
    warehouse_names: dict[UUID, str] = {}
    warehouse_marks: dict[UUID, set[UUID]] = defaultdict(set)
    groups = (
        await session.execute(
            sa.select(DealerGroupMember.dealer_company_id, Company.id, Company.name)
            .join(DealerGroup, DealerGroup.id == DealerGroupMember.dealer_group_id)
            .join(Company, Company.id == DealerGroup.distributor_company_id)
            .where(
                DealerGroupMember.dealer_company_id.in_(company_ids),
                DealerGroup.is_active.is_(True),
            )
        )
    ).all()
    for dealer_id, distributor_id, name in groups:
        distributors[dealer_id].add(distributor_id)
        distributor_names[distributor_id] = name
    rules = (
        (
            await session.execute(
                sa.select(WarehouseAccessRule).where(
                    WarehouseAccessRule.target_id.in_(company_ids),
                    WarehouseAccessRule.is_active.is_(True),
                    WarehouseAccessRule.is_visible.is_(True),
                )
            )
        )
        .scalars()
        .all()
    )
    granted = {rule.warehouse_id for rule in rules}
    warehouses = (
        await session.execute(
            sa.select(
                Warehouse.id,
                Warehouse.owner_company_id,
                WarehouseMark.mark_id,
                City.name,
                Warehouse.address,
            )
            .outerjoin(City, City.id == Warehouse.city_id)
            .outerjoin(WarehouseMark, WarehouseMark.warehouse_id == Warehouse.id)
            .where(
                Warehouse.is_active.is_(True),
                sa.or_(
                    Warehouse.owner_company_id.in_(company_ids),
                    Warehouse.id.in_(granted),
                ),
            )
        )
    ).all()
    for wid, owner_id, mark_id, city, address in warehouses:
        warehouse_names[wid] = ", ".join(value for value in (city, address) if value)
        if owner_id in company_ids:
            own[owner_id].add(wid)
        if mark_id:
            warehouse_marks[wid].add(mark_id)
    products = (
        await session.execute(
            sa.select(
                SpecialEquipmentProduct.warehouse_id, SpecialEquipmentModel.mark_id
            )
            .outerjoin(
                SpecialEquipmentModification,
                SpecialEquipmentModification.id
                == SpecialEquipmentProduct.modification_id,
            )
            .join(
                SpecialEquipmentModel,
                SpecialEquipmentModel.id
                == sa.func.coalesce(
                    SpecialEquipmentModification.model_id,
                    SpecialEquipmentProduct.model_id,
                ),
            )
            .where(SpecialEquipmentProduct.warehouse_id.in_(warehouse_names))
            .distinct()
        )
    ).all()
    for wid, mark_id in products:
        warehouse_marks[wid].add(mark_id)
    for cid, ids in own.items():
        for wid in ids:
            brands[cid].update(warehouse_marks[wid])
    for rule in rules:
        if rule.warehouse_id not in warehouse_names:
            continue
        if rule.brand_id:
            brands[rule.target_id].add(rule.brand_id)
        else:
            brands[rule.target_id].update(warehouse_marks[rule.warehouse_id])
    dist_brands: dict[UUID, set[UUID]] = defaultdict(set)
    rows = (
        await session.execute(
            sa.select(
                DistributorBrand.distributor_company_id, DistributorBrand.brand_id
            ).where(
                DistributorBrand.distributor_company_id.in_(company_ids),
                DistributorBrand.is_active.is_(True),
            )
        )
    ).all()
    for cid, mark_id in rows:
        dist_brands[cid].add(mark_id)
    all_ids = set().union(*brands.values(), *dist_brands.values())
    brand_names = dict(
        (
            await session.execute(
                sa.select(SpecialEquipmentMark.id, SpecialEquipmentMark.name).where(
                    SpecialEquipmentMark.id.in_(all_ids),
                    SpecialEquipmentMark.is_active.is_(True),
                )
            )
        )
        .tuples()
        .all()
    )
    personal: dict[UUID, PersonalAccessRules] = defaultdict(PersonalAccessRules)
    rows_personal = (
        (
            await session.execute(
                sa.select(UserCompanyAccessRule)
                .where(
                    UserCompanyAccessRule.user_company_id.in_(link_ids),
                    UserCompanyAccessRule.is_active.is_(True),
                )
                .order_by(
                    UserCompanyAccessRule.access_object,
                    UserCompanyAccessRule.created_at,
                    UserCompanyAccessRule.id,
                )
            )
        )
        .scalars()
        .all()
    )
    for personal_rule in rows_personal:
        _apply_rule_to_personal_access(
            personal_rule, personal[personal_rule.user_company_id]
        )
    for item in items:
        cid = UUID(item["company_id"])
        access = personal[UUID(item["user_company_id"])]
        base = dist_brands[cid] if item["role"] == "distributor" else brands[cid]
        item["brands"] = _objects(
            _restrict(base, access.brand_mode, access.brand_ids), brand_names
        )
        item["warehouses"] = _objects(
            _restrict(own[cid], access.warehouse_mode, access.warehouse_ids),
            warehouse_names,
        )
        item["distributors"] = _objects(distributors[cid], distributor_names)
