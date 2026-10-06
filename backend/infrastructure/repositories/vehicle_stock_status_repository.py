"""Commercial status facts for already-authorized warehouse vehicle rows."""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.models.applications import ApplicationVehicleAllocation
from infrastructure.models.payments import PurchaseOrder
from infrastructure.models.special_equipment import SpecialEquipmentProduct


async def enrich_stock_status(session: AsyncSession, items: list[dict[str, Any]]) -> None:
    """Enrich only supplied IDs; never expands the caller's inventory scope.

    A raw ``sold`` flag also means an unpaid checkout, so the UI must use
    order facts before labeling the car purchased. No order/user IDs are exposed.
    """
    if not items:
        return
    prod_ids = [item["id"] for item in items if "id" in item]
    if not prod_ids:
        return
    pending = select(PurchaseOrder.id).where(
        PurchaseOrder.product_id == SpecialEquipmentProduct.id,
        PurchaseOrder.status.in_(("reserved", "leasing_pending")),
        PurchaseOrder.paid_amount == 0,
    ).exists()
    completed_purchase = select(PurchaseOrder.id).where(
        PurchaseOrder.product_id == SpecialEquipmentProduct.id,
        PurchaseOrder.status.in_(("purchased", "leasing_active")),
    ).exists()
    completed = completed_purchase | select(ApplicationVehicleAllocation.id).where(
        ApplicationVehicleAllocation.product_id == SpecialEquipmentProduct.id,
        ApplicationVehicleAllocation.completed_at.is_not(None),
        ApplicationVehicleAllocation.released_at.is_(None),
    ).exists()
    # A fast-deal claim has no expiry: ``reserved_until`` stays NULL, which is valid.
    by_fast_deal = select(ApplicationVehicleAllocation.id).where(
        ApplicationVehicleAllocation.product_id == SpecialEquipmentProduct.id,
        ApplicationVehicleAllocation.fast_deal_vehicle_id.is_not(None),
        ApplicationVehicleAllocation.released_at.is_(None),
    ).exists()
    expiry = select(ApplicationVehicleAllocation.reserved_until).where(
        ApplicationVehicleAllocation.product_id == SpecialEquipmentProduct.id,
        ApplicationVehicleAllocation.released_at.is_(None),
        ApplicationVehicleAllocation.completed_at.is_(None),
    ).scalar_subquery()
    rows = (await session.execute(select(
        SpecialEquipmentProduct.id, pending.label("purchase_pending"), completed.label("sale_completed"),
        expiry.label("reserved_until"), by_fast_deal.label("reserved_by_fast_deal"),
    ).where(SpecialEquipmentProduct.id.in_(prod_ids)))).mappings().all()
    states = {row["id"]: dict(row) for row in rows}
    for item in items:
        state = states.get(item["id"])
        if state is not None:
            item.update({key: value for key, value in state.items() if key != "id"})
