"""Canonical physical vehicle owner, shared by access and stock selection."""
from __future__ import annotations

from typing import Any

import sqlalchemy as sa

from infrastructure.models.special_equipment import SpecialEquipmentProduct
from infrastructure.models.vehicles import Warehouse


def resolved_vehicle_owner_expression() -> sa.ColumnElement[Any]:
    """Warehouse ownership takes precedence over seller_company_id."""
    warehouse_owner = (
        sa.select(sa.func.coalesce(Warehouse.company_id, Warehouse.dealer_id))
        .where(Warehouse.id == SpecialEquipmentProduct.warehouse_id)
        .limit(1)
        .correlate(SpecialEquipmentProduct)
        .scalar_subquery()
    )
    return sa.func.coalesce(warehouse_owner, SpecialEquipmentProduct.seller_company_id)
