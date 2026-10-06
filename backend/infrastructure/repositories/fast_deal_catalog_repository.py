"""Catalog facts that fast deal positions are built from.

Read side only: a catalog unit with its owner and directory chain, directory nodes of
a manual position, and the dictionaries of options, purposes and regions. Every
function returns plain dicts and never commits; the rules that judge these facts
live in ``domain.fast_deals.catalog_rules`` and ``application.fast_deals.vehicle_builder``.
"""
from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from infrastructure.models.applications import (
    AdditionalEquipment,
    AdditionalService,
    LeasingPurpose,
    LeasingRegion,
)
from infrastructure.models.special_equipment import (
    SpecialEquipmentCategory,
    SpecialEquipmentColor,
    SpecialEquipmentMark,
    SpecialEquipmentModel,
    SpecialEquipmentModification,
    SpecialEquipmentModificationCategory,
    SpecialEquipmentProduct,
    SpecialEquipmentProductCategory,
    SpecialEquipmentTrim,
)
from infrastructure.models.vehicles import Warehouse
from infrastructure.repositories.vehicle_ownership_repository import (
    resolved_vehicle_owner_expression,
)
from infrastructure.repository_timing import timed_repository

Record = dict[str, Any]

NodeKind = Literal["category", "mark", "model", "modification", "trim", "color"]

# Directory table and the column that links a node to its parent in the chain
# (``None`` for the roots). Colors carry an applicability instead of a parent.
_NODES: dict[str, tuple[Any, str | None]] = {
    "category": (SpecialEquipmentCategory, None),
    "mark": (SpecialEquipmentMark, None),
    "model": (SpecialEquipmentModel, "mark_id"),
    "modification": (SpecialEquipmentModification, "model_id"),
    "trim": (SpecialEquipmentTrim, "modification_id"),
    "color": (SpecialEquipmentColor, None),
}


@timed_repository
async def get_product(session: AsyncSession, product_id: UUID) -> Record | None:
    """A catalog unit with its physical owner, directory chain and category.

    ``owner_company_id`` is the owner of the warehouse, else the seller of the
    listing (the platform's single ownership rule). ``mark_*``/``model_*`` follow the
    listing's own model, else the model of its modification.
    """
    product = SpecialEquipmentProduct
    modification = aliased(SpecialEquipmentModification)
    model = aliased(SpecialEquipmentModel)
    mark = aliased(SpecialEquipmentMark)
    trim = aliased(SpecialEquipmentTrim)
    color = aliased(SpecialEquipmentColor)
    warehouse = aliased(Warehouse)
    row = (
        await session.execute(
            sa.select(
                product.id,
                product.code,
                product.vin,
                product.no_vin,
                product.price,
                product.special_price,
                product.price_on_request,
                product.price_from,
                product.publication_status,
                product.sale_status,
                product.condition,
                product.manufacture_year,
                product.seller_company_id,
                product.warehouse_id,
                product.modification_id,
                product.trim_id,
                product.body_color_id,
                resolved_vehicle_owner_expression().label("owner_company_id"),
                model.id.label("model_id"),
                model.name.label("model_name"),
                model.category_id.label("model_category_id"),
                mark.id.label("mark_id"),
                mark.name.label("mark_name"),
                modification.name.label("modification_name"),
                trim.name.label("trim_name"),
                color.name.label("body_color_name"),
                warehouse.name.label("warehouse_name"),
            )
            .select_from(product)
            .outerjoin(modification, modification.id == product.modification_id)
            .outerjoin(
                model, model.id == sa.func.coalesce(product.model_id, modification.model_id)
            )
            .outerjoin(mark, mark.id == model.mark_id)
            .outerjoin(trim, trim.id == product.trim_id)
            .outerjoin(color, color.id == product.body_color_id)
            .outerjoin(warehouse, warehouse.id == product.warehouse_id)
            .where(product.id == product_id)
        )
    ).mappings().first()
    if row is None:
        return None
    result = dict(row)
    category_id, category_name = await _product_category(
        session,
        product_id,
        modification_id=result["modification_id"],
        model_category_id=result["model_category_id"],
    )
    result["category_id"] = category_id
    result["category_name"] = category_name
    return result


async def _product_category(
    session: AsyncSession,
    product_id: UUID,
    *,
    modification_id: UUID | None,
    model_category_id: UUID | None,
) -> tuple[UUID | None, str | None]:
    """The category a unit is registered under.

    A unit may be advertised in several categories: the primary category of its
    modification wins when the unit is advertised there, else the first by the
    directory order. Without own categories the modification's primary category and
    then the model's category are used.
    """
    category = SpecialEquipmentCategory
    own = (
        await session.execute(
            sa.select(category.id, category.name)
            .join(
                SpecialEquipmentProductCategory,
                SpecialEquipmentProductCategory.category_id == category.id,
            )
            .where(
                SpecialEquipmentProductCategory.product_id == product_id,
                category.is_active.is_(True),
            )
            .order_by(category.sort_order, category.name, category.id)
        )
    ).all()
    primary_id: UUID | None = None
    if modification_id is not None:
        primary_id = await session.scalar(
            sa.select(SpecialEquipmentModificationCategory.category_id).where(
                SpecialEquipmentModificationCategory.modification_id == modification_id,
                SpecialEquipmentModificationCategory.is_primary.is_(True),
            )
        )
    if own:
        chosen = next((item for item in own if item.id == primary_id), own[0])
        return chosen.id, chosen.name
    fallback_id = primary_id or model_category_id
    if fallback_id is None:
        return None, None
    name = await session.scalar(sa.select(category.name).where(category.id == fallback_id))
    return (fallback_id, name) if name is not None else (None, None)


@timed_repository
async def get_directory_node(
    session: AsyncSession, kind: NodeKind, node_id: UUID
) -> Record | None:
    """One directory row: ``{id, name, is_active, parent_id, applicability}``.

    ``parent_id`` is the mark of a model, the model of a modification or the
    modification of a trim; ``applicability`` is set for colors only.
    """
    table, parent = _NODES[kind]
    columns: list[Any] = [table.id, table.name, table.is_active]
    if parent is not None:
        columns.append(getattr(table, parent).label("parent_id"))
    if kind == "color":
        columns.append(table.applicability)
    row = (await session.execute(sa.select(*columns).where(table.id == node_id))).mappings().first()
    if row is None:
        return None
    return {
        "id": row["id"],
        "name": row["name"],
        "is_active": bool(row["is_active"]),
        "parent_id": row["parent_id"] if parent is not None else None,
        "applicability": row["applicability"] if kind == "color" else None,
    }


# ------------------------------------------------------------------------ dictionaries

@timed_repository
async def equipment_names(session: AsyncSession, codes: list[str]) -> dict[str, str]:
    """``code → display name`` of the active additional equipment among ``codes``."""
    if not codes:
        return {}
    rows = await session.execute(
        sa.select(AdditionalEquipment.equipment_code, AdditionalEquipment.equipment_display_name)
        .where(
            AdditionalEquipment.equipment_code.in_(codes),
            AdditionalEquipment.is_active.is_(True),
        )
    )
    return dict(rows.tuples().all())


@timed_repository
async def service_names(session: AsyncSession, codes: list[str]) -> dict[str, str]:
    """``code → display name`` of the active additional services among ``codes``."""
    if not codes:
        return {}
    rows = await session.execute(
        sa.select(AdditionalService.service_code, AdditionalService.service_display_name)
        .where(
            AdditionalService.service_code.in_(codes),
            AdditionalService.is_active.is_(True),
        )
    )
    return dict(rows.tuples().all())


@timed_repository
async def purpose_names(session: AsyncSession, names: list[str]) -> set[str]:
    """The ``purpose_name`` values among ``names`` that exist in the dictionary."""
    if not names:
        return set()
    rows = await session.scalars(
        sa.select(LeasingPurpose.purpose_name).where(LeasingPurpose.purpose_name.in_(names))
    )
    return set(rows.all())


@timed_repository
async def region_names(session: AsyncSession, names: list[str]) -> set[str]:
    """The ``region_name`` values among ``names`` that exist in the dictionary."""
    if not names:
        return set()
    rows = await session.scalars(
        sa.select(LeasingRegion.region_name).where(LeasingRegion.region_name.in_(names))
    )
    return set(rows.all())
