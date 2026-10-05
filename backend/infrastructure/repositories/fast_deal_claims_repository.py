"""Global reserve of catalog units for fast deals: product locks, claims, allocations.

A fast-deal claim is an ``application_vehicle_allocations`` row that points at the
position (``fast_deal_vehicle_id``) and has no ``reserved_until``: it never expires
by itself. The same table holds the claims of ordinary applications, so the unique
index on the open allocation of a product is the last guard against two winners.

Every function returns plain dicts, never commits, and expects the caller to hold
the deal lock. Products are locked in ascending id order, the order that ordinary
reservations use, so reservations of different sources cannot deadlock.
"""
from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Literal, cast
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.models.applications import (
    ApplicationVehicleAllocation as Allocation,
)
from infrastructure.models.fast_deals import FastDeal, FastDealVehicle
from infrastructure.models.payments import PurchaseOrder
from infrastructure.models.special_equipment import SpecialEquipmentProduct as Product
from infrastructure.models.special_equipment_commerce import (
    SpecialEquipmentApplicationItem,
    SpecialEquipmentOrderItem,
    SpecialEquipmentPurchaseOrder,
)
from infrastructure.repositories import vehicle_fulfillment_repository as fulfillment
from infrastructure.repositories.fast_deal_access_repository import Scope, scope_clause
from infrastructure.repositories.vehicle_ownership_repository import (
    resolved_vehicle_owner_expression,
)
from infrastructure.repository_timing import timed_repository

if TYPE_CHECKING:
    from sqlalchemy.engine import CursorResult

Record = dict[str, Any]
# Why a unit could not be claimed although every check passed under the lock.
ClaimFailure = Literal["claimed", "unavailable", "price"]

# Orders that own a unit exclusively (same set as the catalog's own release guard).
_LIVE_ORDER_STATUSES = (
    "payment_pending",
    "reserved",
    "purchased",
    "leasing_pending",
    "leasing_active",
    "cancellation_requested",
)
_UNIQUE_CLAIM = "uq_vehicle_active_allocation"


def _rowcount(result: Any) -> int:
    return int(cast("CursorResult[Any]", result).rowcount or 0)


def _status_update(*, source: str, target: str) -> Any:
    """Move a unit between sale statuses; the catalog's lock version follows."""
    return (
        sa.update(Product)
        .where(Product.sale_status == source)
        .values(
            sale_status=target,
            lock_version=Product.lock_version + 1,
            updated_at=sa.func.now(),
        )
        .execution_options(synchronize_session=False)
    )


@timed_repository
async def lock_products(session: AsyncSession, product_ids: Iterable[UUID]) -> dict[UUID, Record]:
    """Lock the units ``FOR UPDATE`` in id order and return what a claim must verify.

    ``owner_company_id`` is the canonical physical owner: the warehouse owner, else
    the seller of the listing.
    """
    ids = sorted(set(product_ids))
    if not ids:
        return {}
    rows = await session.execute(
        sa.select(
            Product.id,
            Product.vin,
            Product.no_vin,
            Product.publication_status,
            Product.sale_status,
            Product.price,
            Product.price_on_request,
            Product.price_from,
            resolved_vehicle_owner_expression().label("owner_company_id"),
        )
        .where(Product.id.in_(ids))
        .order_by(Product.id)
        .with_for_update(of=Product)
    )
    return {row["id"]: dict(row) for row in rows.mappings()}


@timed_repository
async def active_allocations(
    session: AsyncSession, product_ids: Iterable[UUID], *, visible_to: Scope
) -> dict[UUID, Record]:
    """Open claims (completed ones included) on the units, whatever their source.

    ``fast_deal_number`` is filled only for a fast deal that ``visible_to`` may see,
    so a conflict never reveals the number or the client of someone else's source.
    """
    ids = sorted(set(product_ids))
    if not ids:
        return {}
    rows = await session.execute(
        sa.select(
            Allocation.product_id,
            Allocation.application_vehicle_id,
            Allocation.fast_deal_vehicle_id,
            Allocation.completed_at,
            FastDealVehicle.fast_deal_id,
        )
        .select_from(Allocation)
        .outerjoin(FastDealVehicle, FastDealVehicle.id == Allocation.fast_deal_vehicle_id)
        .where(Allocation.product_id.in_(ids), Allocation.released_at.is_(None))
    )
    claims = {row["product_id"]: dict(row) for row in rows.mappings()}
    deal_ids = {c["fast_deal_id"] for c in claims.values() if c["fast_deal_id"] is not None}
    visible: dict[UUID, str] = {}
    if deal_ids:
        found = await session.execute(
            sa.select(FastDeal.id, FastDeal.display_number).where(
                FastDeal.id.in_(deal_ids), scope_clause(visible_to)
            )
        )
        visible = dict(found.tuples().all())
    for claim in claims.values():
        claim["fast_deal_number"] = visible.get(claim["fast_deal_id"])
    return claims


@timed_repository
async def commerce_claims(session: AsyncSession, product_ids: Iterable[UUID]) -> set[UUID]:
    """Units held by a purchase, a live order or a leasing item that reached reserve.

    Allocations are read by ``active_allocations``. A unit that merely sits in an
    unreserved cart or in a preorder is not claimed.
    """
    ids = sorted(set(product_ids))
    if not ids:
        return set()
    live_order = sa.and_(
        SpecialEquipmentPurchaseOrder.purchase_type != "preorder",
        SpecialEquipmentPurchaseOrder.status.in_(_LIVE_ORDER_STATUSES),
    )
    rows = await session.execute(
        sa.union(
            sa.select(PurchaseOrder.product_id).where(
                PurchaseOrder.product_id.in_(ids), PurchaseOrder.status != "cancelled"
            ),
            sa.select(SpecialEquipmentPurchaseOrder.product_id).where(
                SpecialEquipmentPurchaseOrder.product_id.in_(ids), live_order
            ),
            sa.select(SpecialEquipmentOrderItem.product_id)
            .join(
                SpecialEquipmentPurchaseOrder,
                SpecialEquipmentPurchaseOrder.id == SpecialEquipmentOrderItem.purchase_order_id,
            )
            .where(SpecialEquipmentOrderItem.product_id.in_(ids), live_order),
            sa.select(SpecialEquipmentApplicationItem.product_id).where(
                SpecialEquipmentApplicationItem.product_id.in_(ids),
                SpecialEquipmentApplicationItem.item_status == "reserved",
            ),
        )
    )
    return {row[0] for row in rows}


@timed_repository
async def claim_unit(
    session: AsyncSession,
    *,
    product_id: UUID,
    vehicle_id: UUID,
    vin: str,
    unit_price: Decimal,
    created_by: UUID,
) -> ClaimFailure | None:
    """Insert the allocation, then mark the unit ``reserved``; ``None`` on success.

    The allocation goes first: the catalog guard for request-priced units demands an
    allocation with a positive price before the status may become ``reserved``. Both
    writes share a savepoint, so a rejected claim leaves nothing behind.
    """
    stage = "claim"
    savepoint = await session.begin_nested()
    try:
        await session.execute(
            sa.insert(Allocation).values(
                fast_deal_vehicle_id=vehicle_id,
                product_id=product_id,
                vin=vin,
                unit_price=unit_price,
                reserved_until=None,
                created_by=created_by,
            )
        )
        stage = "status"
        result = await session.execute(
            _status_update(source="available", target="reserved").where(Product.id == product_id)
        )
    except IntegrityError as exc:
        await savepoint.rollback()
        if stage == "claim" and _UNIQUE_CLAIM in str(exc.orig):
            return "claimed"
        if stage == "status":
            return "price"
        raise
    if _rowcount(result) != 1:
        await savepoint.rollback()
        return "unavailable"
    await savepoint.commit()
    return None


async def _release(session: AsyncSession, condition: Any, reason: str) -> list[UUID]:
    open_claims = (
        await session.execute(
            sa.select(Allocation.id, Allocation.product_id)
            .join(FastDealVehicle, FastDealVehicle.id == Allocation.fast_deal_vehicle_id)
            .where(condition, Allocation.released_at.is_(None), Allocation.completed_at.is_(None))
        )
    ).all()
    if not open_claims:
        return []
    product_ids = sorted({product_id for _, product_id in open_claims})
    await lock_products(session, product_ids)
    await session.execute(
        sa.update(Allocation)
        .where(
            Allocation.id.in_([claim_id for claim_id, _ in open_claims]),
            Allocation.released_at.is_(None),
            Allocation.completed_at.is_(None),
        )
        .values(released_at=datetime.now(UTC), release_reason=reason)
        .execution_options(synchronize_session=False)
    )
    return product_ids


@timed_repository
async def release_deal_claims(session: AsyncSession, deal_id: UUID, *, reason: str) -> list[UUID]:
    """Release the open, not completed claims of a deal; returns the freed units."""
    return await _release(session, FastDealVehicle.fast_deal_id == deal_id, reason)


@timed_repository
async def release_vehicle_claims(
    session: AsyncSession, vehicle_id: UUID, *, reason: str
) -> list[UUID]:
    """Release the open, not completed claim of one position; returns the freed units."""
    return await _release(session, FastDealVehicle.id == vehicle_id, reason)


@timed_repository
async def restore_available(session: AsyncSession, product_ids: Iterable[UUID]) -> list[UUID]:
    """Return ``reserved`` units to stock when nothing else claims them.

    A ``sold`` unit is never touched: a completed claim is still an open allocation,
    and ``has_conflicting_claim`` sees it.
    """
    ids = sorted(set(product_ids))
    held: set[UUID] = await commerce_claims(session, ids)
    restored: list[UUID] = []
    for product_id in ids:
        if product_id in held or await fulfillment.has_conflicting_claim(session, product_id):
            continue
        result = await session.execute(
            _status_update(source="reserved", target="available").where(Product.id == product_id)
        )
        if _rowcount(result):
            restored.append(product_id)
    return restored


@timed_repository
async def deal_allocations(session: AsyncSession, deal_id: UUID) -> list[Record]:
    """Open allocations of the deal's positions, completed ones included."""
    rows = await session.execute(
        sa.select(
            Allocation.id,
            Allocation.product_id,
            Allocation.fast_deal_vehicle_id,
            Allocation.completed_at,
        )
        .join(FastDealVehicle, FastDealVehicle.id == Allocation.fast_deal_vehicle_id)
        .where(FastDealVehicle.fast_deal_id == deal_id, Allocation.released_at.is_(None))
    )
    return [dict(row) for row in rows.mappings()]


@timed_repository
async def complete_allocations(session: AsyncSession, allocation_ids: Iterable[UUID]) -> None:
    """Mark claims completed: the unit is consumed by the confirmed deal."""
    ids = list(allocation_ids)
    if not ids:
        return
    await session.execute(
        sa.update(Allocation)
        .where(Allocation.id.in_(ids), Allocation.completed_at.is_(None))
        .values(completed_at=datetime.now(UTC))
        .execution_options(synchronize_session=False)
    )


@timed_repository
async def mark_sold(session: AsyncSession, product_ids: Iterable[UUID]) -> None:
    """``reserved`` units of a confirmed deal become ``sold``."""
    ids = list(product_ids)
    if not ids:
        return
    await session.execute(
        _status_update(source="reserved", target="sold").where(Product.id.in_(ids))
    )
