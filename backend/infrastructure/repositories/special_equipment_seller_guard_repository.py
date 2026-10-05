"""Cross-domain read model for safe company-seller deactivation."""

from __future__ import annotations

from typing import Any, TypedDict
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.models.special_equipment import SpecialEquipmentProduct
from infrastructure.models.special_equipment_commerce import (
    SpecialEquipmentApplicationItem,
    SpecialEquipmentPurchaseOrder,
)
from infrastructure.repository_timing import timed_repository

_LIVE_APPLICATION_STATUSES = ("active", "reserved")
_LIVE_ORDER_STATUSES = (
    "payment_pending",
    "reserved",
    "purchased",
    "leasing_pending",
    "leasing_active",
    "cancellation_requested",
)


class SellerDeactivationBlockers(TypedDict):
    published_products: int
    claimed_products: int
    live_application_items: int
    live_purchase_orders: int


def seller_deactivation_blocker_statement(company_id: UUID) -> Any:
    """Build an indexable blocker query, including nullable legacy snapshots."""
    application_direct = (
        sa.select(sa.func.count())
        .select_from(SpecialEquipmentApplicationItem)
        .where(
            SpecialEquipmentApplicationItem.seller_company_id == company_id,
            SpecialEquipmentApplicationItem.item_status.in_(
                _LIVE_APPLICATION_STATUSES
            ),
        )
        .scalar_subquery()
    )
    application_legacy = (
        sa.select(sa.func.count())
        .select_from(SpecialEquipmentApplicationItem)
        .join(
            SpecialEquipmentProduct,
            SpecialEquipmentProduct.id == SpecialEquipmentApplicationItem.product_id,
        )
        .where(
            SpecialEquipmentApplicationItem.seller_company_id.is_(None),
            SpecialEquipmentProduct.seller_company_id == company_id,
            SpecialEquipmentApplicationItem.item_status.in_(
                _LIVE_APPLICATION_STATUSES
            ),
        )
        .scalar_subquery()
    )
    order_direct = (
        sa.select(sa.func.count())
        .select_from(SpecialEquipmentPurchaseOrder)
        .where(
            SpecialEquipmentPurchaseOrder.seller_company_id == company_id,
            SpecialEquipmentPurchaseOrder.status.in_(_LIVE_ORDER_STATUSES),
        )
        .scalar_subquery()
    )
    order_legacy = (
        sa.select(sa.func.count())
        .select_from(SpecialEquipmentPurchaseOrder)
        .join(
            SpecialEquipmentProduct,
            SpecialEquipmentProduct.id == SpecialEquipmentPurchaseOrder.product_id,
        )
        .where(
            SpecialEquipmentPurchaseOrder.seller_company_id.is_(None),
            SpecialEquipmentProduct.seller_company_id == company_id,
            SpecialEquipmentPurchaseOrder.status.in_(_LIVE_ORDER_STATUSES),
        )
        .scalar_subquery()
    )
    return sa.select(
        sa.select(sa.func.count())
        .select_from(SpecialEquipmentProduct)
        .where(
            SpecialEquipmentProduct.seller_company_id == company_id,
            SpecialEquipmentProduct.publication_status == "published",
        )
        .scalar_subquery()
        .label("published_products"),
        sa.select(sa.func.count())
        .select_from(SpecialEquipmentProduct)
        .where(
            SpecialEquipmentProduct.seller_company_id == company_id,
            SpecialEquipmentProduct.sale_status.in_(("reserved", "sold")),
        )
        .scalar_subquery()
        .label("claimed_products"),
        (application_direct + application_legacy).label("live_application_items"),
        (order_direct + order_legacy).label("live_purchase_orders"),
    )


@timed_repository
async def seller_deactivation_blockers(
    session: AsyncSession, company_id: UUID
) -> SellerDeactivationBlockers:
    """Return only live references that require an active seller.

    Historical terminal commerce rows, favorites, and cart items deliberately
    do not block company deactivation. Nullable legacy commerce seller values
    fall back to the product's current seller.
    """
    row = (
        await session.execute(seller_deactivation_blocker_statement(company_id))
    ).mappings().one()
    return SellerDeactivationBlockers(
        published_products=int(row["published_products"] or 0),
        claimed_products=int(row["claimed_products"] or 0),
        live_application_items=int(row["live_application_items"] or 0),
        live_purchase_orders=int(row["live_purchase_orders"] or 0),
    )


def has_seller_deactivation_blockers(
    blockers: SellerDeactivationBlockers,
) -> bool:
    return any(blockers.values())
