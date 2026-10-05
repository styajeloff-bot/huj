"""Intentional SQL seam for public catalog storefront membership."""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from sqlalchemy import exists, select, true

from domain.storefronts import DEFAULT_STOREFRONT_ID, CatalogScope
from infrastructure.models.special_equipment import (
    SpecialEquipmentProduct,
)
from infrastructure.models.storefronts import Storefront, StorefrontWarehouse
from infrastructure.models.vehicles import Warehouse


def vehicle_visible_in(
    scope: CatalogScope,
    *,
    vehicle: Any = SpecialEquipmentProduct,
) -> Any:
    """Compatibility alias for special equipment visibility."""
    return special_equipment_visible_in(scope, product=vehicle)


def special_equipment_visible_in(
    scope: CatalogScope,
    *,
    product: Any = SpecialEquipmentProduct,
) -> Any:
    """Return the active warehouse-membership predicate for special equipment."""

    if scope.is_default:
        return true()

    effective_warehouse_id = _special_equipment_effective_warehouse_id(product)
    return exists(
        select(StorefrontWarehouse.storefront_id)
        .select_from(StorefrontWarehouse)
        .join(Warehouse, Warehouse.id == StorefrontWarehouse.warehouse_id)
        .where(
            StorefrontWarehouse.storefront_id == scope.id,
            Warehouse.status == "active",
            effective_warehouse_id == Warehouse.id,
        )
    )


def special_equipment_visible_for_storefront(
    storefront_id: Any,
    *,
    product: Any = SpecialEquipmentProduct,
) -> Any:
    """Return a projection predicate from a persisted storefront FK."""

    effective_warehouse_id = _special_equipment_effective_warehouse_id(product)
    return sa.or_(
        storefront_id == DEFAULT_STOREFRONT_ID,
        exists(
            select(StorefrontWarehouse.storefront_id)
            .select_from(StorefrontWarehouse)
            .join(Storefront, Storefront.id == StorefrontWarehouse.storefront_id)
            .join(Warehouse, Warehouse.id == StorefrontWarehouse.warehouse_id)
            .where(
                StorefrontWarehouse.storefront_id == storefront_id,
                Storefront.is_active.is_(True),
                Warehouse.status == "active",
                effective_warehouse_id == Warehouse.id,
            )
        ),
    )


def _special_equipment_effective_warehouse_id(product: Any) -> Any:
    return product.warehouse_id
