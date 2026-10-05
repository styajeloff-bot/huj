"""Warehouse access rule repository — async, dict-only API.

Handles role-scoped access rule management for warehouses.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from domain.errors import InvalidWarehouseError
from infrastructure.models.companies import Company
from infrastructure.models.special_equipment import (
    SpecialEquipmentMark,
    SpecialEquipmentModel,
    SpecialEquipmentModification,
    SpecialEquipmentProduct,
)
from infrastructure.models.storefronts import Storefront
from infrastructure.models.support import DealerGroup, DealerGroupMember
from infrastructure.models.vehicles import Warehouse, WarehouseAccessRule
from infrastructure.repository_timing import timed_repository


def _rule_to_dict(
    rule: WarehouseAccessRule,
    *,
    warehouse_name: str,
    target_name: str,
    site_name: str | None = None,
    brand_name: str | None = None,
    source_group_name: str | None = None,
    owner_company_id: UUID | None = None,
    owner_company_name: str | None = None,
    owner_company_type: str | None = None,
    warehouse_brand_names: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "id": str(rule.id),
        "warehouse_id": str(rule.warehouse_id),
        "warehouse_name": warehouse_name,
        "owner_company_id": str(owner_company_id) if owner_company_id else None,
        "owner_company_name": owner_company_name,
        "owner_company_type": owner_company_type,
        "warehouse_brand_names": warehouse_brand_names or [],
        "target_type": rule.target_type,
        "target_id": str(rule.target_id),
        "target_name": target_name,
        "warehouse_access_type": rule.warehouse_access_type,
        "site_id": str(rule.site_id) if rule.site_id else None,
        "site_name": site_name,
        "brand_id": str(rule.brand_id) if rule.brand_id else None,
        "brand_name": brand_name,
        "source_group_id": str(rule.source_group_id) if rule.source_group_id else None,
        "source_group_name": source_group_name,
        "is_visible": rule.is_visible,
        "can_create_application": rule.can_create_application,
        "is_active": rule.is_active,
        "created_at": rule.created_at,
        "updated_at": rule.updated_at,
    }


@timed_repository
async def get_rule_by_id(
    session: AsyncSession,
    rule_id: UUID,
) -> dict[str, Any] | None:
    owner_company = aliased(Company, name="owner_company")
    stmt = (
        select(
            WarehouseAccessRule,
            Warehouse.name.label("warehouse_name"),
            Warehouse.owner_company_id.label("owner_company_id"),
            Warehouse.owner_company_type.label("owner_company_type"),
            owner_company.name.label("owner_company_name"),
            Company.name.label("target_name"),
            func.coalesce(Storefront.slug, "Основная витрина").label("site_name"),
            SpecialEquipmentMark.name.label("brand_name"),
            DealerGroup.name.label("source_group_name"),
        )
        .join(Warehouse, Warehouse.id == WarehouseAccessRule.warehouse_id)
        .outerjoin(owner_company, owner_company.id == Warehouse.owner_company_id)
        .join(Company, Company.id == WarehouseAccessRule.target_id)
        .outerjoin(Storefront, Storefront.id == WarehouseAccessRule.site_id)
        .outerjoin(SpecialEquipmentMark, SpecialEquipmentMark.id == WarehouseAccessRule.brand_id)
        .outerjoin(DealerGroup, DealerGroup.id == WarehouseAccessRule.source_group_id)
        .where(WarehouseAccessRule.id == rule_id)
    )
    result = (await session.execute(stmt)).first()
    if result is None:
        return None
    (
        rule,
        wh_name,
        owner_company_id,
        owner_company_type,
        owner_company_name,
        target_name,
        site_name,
        brand_name,
        source_group_name,
    ) = result

    # Hydrate warehouse vehicle marks
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
        .where(SpecialEquipmentProduct.warehouse_id == rule.warehouse_id)
        .distinct()
        .order_by(SpecialEquipmentMark.name.asc())
    )
    warehouse_brand_names = list((await session.execute(marks_stmt)).scalars().all())

    return _rule_to_dict(
        rule,
        warehouse_name=wh_name,
        target_name=target_name,
        site_name=site_name,
        brand_name=brand_name,
        source_group_name=source_group_name,
        owner_company_id=owner_company_id,
        owner_company_name=owner_company_name,
        owner_company_type=owner_company_type,
        warehouse_brand_names=warehouse_brand_names,
    )


@timed_repository
async def list_access_rules(
    session: AsyncSession,
    *,
    warehouse_id: UUID | None = None,
    actor_filter: list[UUID] | None = None,
    is_active: bool | None = None,
    page: int = 1,
    limit: int = 20,
) -> tuple[list[dict[str, Any]], int]:
    """List access rules with scope gating and hydrated relation names."""
    if actor_filter == []:
        return [], 0

    conditions = []
    if warehouse_id is not None:
        conditions.append(WarehouseAccessRule.warehouse_id == warehouse_id)
    if is_active is not None:
        conditions.append(WarehouseAccessRule.is_active == is_active)
    if actor_filter is not None:
        # Non-admin actors only see rules for warehouses their companies own
        conditions.append(Warehouse.owner_company_id.in_(actor_filter))

    where_clause = sa.and_(*conditions) if conditions else None

    count_stmt = (
        select(func.count(WarehouseAccessRule.id))
        .join(Warehouse, Warehouse.id == WarehouseAccessRule.warehouse_id)
    )
    if where_clause is not None:
        count_stmt = count_stmt.where(where_clause)
    total = int((await session.execute(count_stmt)).scalar() or 0)

    owner_company = aliased(Company, name="owner_company")
    list_stmt = (
        select(
            WarehouseAccessRule,
            Warehouse.name.label("warehouse_name"),
            Warehouse.owner_company_id.label("owner_company_id"),
            Warehouse.owner_company_type.label("owner_company_type"),
            owner_company.name.label("owner_company_name"),
            Company.name.label("target_name"),
            func.coalesce(Storefront.slug, "Основная витрина").label("site_name"),
            SpecialEquipmentMark.name.label("brand_name"),
            DealerGroup.name.label("source_group_name"),
        )
        .join(Warehouse, Warehouse.id == WarehouseAccessRule.warehouse_id)
        .outerjoin(owner_company, owner_company.id == Warehouse.owner_company_id)
        .join(Company, Company.id == WarehouseAccessRule.target_id)
        .outerjoin(Storefront, Storefront.id == WarehouseAccessRule.site_id)
        .outerjoin(SpecialEquipmentMark, SpecialEquipmentMark.id == WarehouseAccessRule.brand_id)
        .outerjoin(DealerGroup, DealerGroup.id == WarehouseAccessRule.source_group_id)
        .order_by(WarehouseAccessRule.created_at.desc(), WarehouseAccessRule.id.desc())
    )
    if where_clause is not None:
        list_stmt = list_stmt.where(where_clause)
    list_stmt = list_stmt.offset((page - 1) * limit).limit(limit)

    rows = (await session.execute(list_stmt)).all()
    if not rows:
        return [], total

    # Batch hydrate warehouse vehicle marks
    wh_ids = list({row[0].warehouse_id for row in rows})
    marks_stmt = (
        select(SpecialEquipmentProduct.warehouse_id, SpecialEquipmentMark.name)
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
        .where(SpecialEquipmentProduct.warehouse_id.in_(wh_ids))
        .distinct()
        .order_by(SpecialEquipmentMark.name.asc())
    )
    marks_rows = (await session.execute(marks_stmt)).all()
    wh_marks_map: dict[UUID, list[str]] = {wid: [] for wid in wh_ids}
    for wid, mark_name in marks_rows:
        if wid is not None and mark_name:
            wh_marks_map.setdefault(wid, []).append(mark_name)

    items = []
    for row in rows:
        rule = row[0]
        wh_marks = wh_marks_map.get(rule.warehouse_id, [])
        items.append(
            _rule_to_dict(
                rule,
                warehouse_name=row[1],
                target_name=row[5],
                site_name=row[6],
                brand_name=row[7],
                source_group_name=row[8],
                owner_company_id=row[2],
                owner_company_type=row[3],
                owner_company_name=row[4],
                warehouse_brand_names=wh_marks,
            )
        )
    return items, total


@timed_repository
async def create_or_upsert_rules(  # noqa: PLR0912
    session: AsyncSession,
    *,
    warehouse_id: UUID,
    mode: str,
    dealers: list[dict[str, Any]] | None = None,
    dealer_group_id: UUID | None = None,
    group_access_type: str = "B",
    site_id: UUID | None = None,
    brand_id: UUID | None = None,
) -> list[dict[str, Any]]:
    items_to_apply: list[dict[str, Any]] = []
    if mode == "dealer_group":
        if dealer_group_id is None:
            raise InvalidWarehouseError("Не указана группа дилеров")
        warehouse = await session.get(Warehouse, warehouse_id)
        if warehouse is None:
            raise InvalidWarehouseError("Склад не найден")
        dealer_group = await session.get(DealerGroup, dealer_group_id)
        if dealer_group is None:
            raise InvalidWarehouseError("Группа дилеров не найдена")
        if (
            warehouse.owner_company_type == "distributor"
            and dealer_group.distributor_company_id != warehouse.owner_company_id
        ):
            raise InvalidWarehouseError(
                "Группа дилеров должна принадлежать дистрибьютору-владельцу склада"
            )
        members_stmt = select(DealerGroupMember.dealer_company_id).where(
            DealerGroupMember.dealer_group_id == dealer_group_id
        )
        member_ids = list((await session.execute(members_stmt)).scalars().all())
        items_to_apply.extend(
            {
                "dealer_id": member_id,
                "access_type": group_access_type,
                "source_group_id": dealer_group_id,
            }
            for member_id in member_ids
        )
    elif mode == "dealers":
        if not dealers:
            raise InvalidWarehouseError("Не указаны дилеры для предоставления доступа")
        items_to_apply.extend(
            {
                "dealer_id": dealer["dealer_id"],
                "access_type": dealer.get("access_type", "B"),
                "source_group_id": None,
            }
            for dealer in dealers
        )
    else:
        raise InvalidWarehouseError(f"Неизвестный режим создания правил: {mode}")

    rule_ids: list[UUID] = []
    now = datetime.now(UTC)

    for item in items_to_apply:
        did = item["dealer_id"]
        acc_type = item["access_type"]
        can_app = (acc_type == "B")
        src_grp = item["source_group_id"]

        rule_stmt = select(WarehouseAccessRule).where(
            WarehouseAccessRule.warehouse_id == warehouse_id,
            WarehouseAccessRule.target_type == "dealer",
            WarehouseAccessRule.target_id == did,
            WarehouseAccessRule.site_id.is_(site_id) if site_id is None else WarehouseAccessRule.site_id == site_id,
            WarehouseAccessRule.brand_id.is_(brand_id) if brand_id is None else WarehouseAccessRule.brand_id == brand_id,
        )
        existing = (await session.execute(rule_stmt)).scalar_one_or_none()
        if existing is not None:
            existing.warehouse_access_type = acc_type
            existing.can_create_application = can_app
            existing.source_group_id = src_grp
            existing.is_active = True
            cast("Any", existing).updated_at = now
            rule_ids.append(existing.id)
        else:
            new_rule = WarehouseAccessRule(
                warehouse_id=warehouse_id,
                target_type="dealer",
                target_id=did,
                warehouse_access_type=acc_type,
                site_id=site_id,
                brand_id=brand_id,
                source_group_id=src_grp,
                is_visible=True,
                can_create_application=can_app,
                is_active=True,
            )
            session.add(new_rule)
            await session.flush()
            rule_ids.append(new_rule.id)

    await session.flush()

    hydrated_rules: list[dict[str, Any]] = []
    for rid in rule_ids:
        hydrated = await get_rule_by_id(session, rid)
        if hydrated is not None:
            hydrated_rules.append(hydrated)
    return hydrated_rules


@timed_repository
async def update_access_rule(
    session: AsyncSession,
    rule_id: UUID,
    *,
    warehouse_access_type: str | None = None,
    is_active: bool | None = None,
    actor_role: str | None = None,
) -> dict[str, Any] | None:
    rule = await session.get(WarehouseAccessRule, rule_id)
    if rule is None:
        return None

    if rule.warehouse_access_type == "A" and actor_role != "carcraft_employee":
        if warehouse_access_type is not None and warehouse_access_type != "A":
            raise InvalidWarehouseError("Запрещено изменять базовое правило доступа типа A")
        if is_active is not None and not is_active:
            raise InvalidWarehouseError("Запрещено отключать базовое правило доступа типа A")

    if warehouse_access_type is not None:
        rule.warehouse_access_type = warehouse_access_type
        rule.can_create_application = (warehouse_access_type == "B")
    if is_active is not None:
        rule.is_active = is_active

    cast("Any", rule).updated_at = datetime.now(UTC)
    await session.flush()
    return await get_rule_by_id(session, rule_id)


@timed_repository
async def delete_access_rule(
    session: AsyncSession,
    rule_id: UUID,
    *,
    actor_role: str | None = None,
) -> bool:
    rule = await session.get(WarehouseAccessRule, rule_id)
    if rule is None:
        return False
    if rule.warehouse_access_type == "A" and actor_role != "carcraft_employee":
        raise InvalidWarehouseError("Запрещено удалять базовое правило доступа типа A")
    await session.delete(rule)
    await session.flush()
    return True
