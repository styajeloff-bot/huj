"""Locked physical-stock allocation persistence and read models."""
from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.models.applications import (
    ApplicationVehicle,
    ApplicationVehicleAllocation,
    ApplicationVehicleFulfillmentHistory,
    LeasingApplication,
)
from infrastructure.models.payments import PurchaseOrder
from infrastructure.models.special_equipment import SpecialEquipmentProduct
from infrastructure.repositories.vehicle_ownership_repository import (
    resolved_vehicle_owner_expression,
)


def _dict(row: Any) -> dict[str, Any]:
    d = {column.name: getattr(row, column.name) for column in row.__table__.columns}
    if "product_id" in d and "vehicle_id" not in d:
        d["vehicle_id"] = d["product_id"]
    return d


async def line(session: AsyncSession, line_id: UUID, *, lock: bool = False) -> dict[str, Any] | None:
    if lock:
        await session.execute(sa.select(LeasingApplication.id).join(ApplicationVehicle,
            ApplicationVehicle.application_id == LeasingApplication.id).where(
            ApplicationVehicle.id == line_id).with_for_update(of=LeasingApplication))
    stmt = sa.select(ApplicationVehicle).where(ApplicationVehicle.id == line_id)
    if lock:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    row = await session.scalar(stmt)
    return _dict(row) if row else None


async def allocations(session: AsyncSession, line_id: UUID, *, active_only: bool = False) -> list[dict[str, Any]]:
    stmt = sa.select(ApplicationVehicleAllocation).where(ApplicationVehicleAllocation.application_vehicle_id == line_id)
    if active_only:
        stmt = stmt.where(ApplicationVehicleAllocation.released_at.is_(None))
    rows = (await session.scalars(stmt.order_by(ApplicationVehicleAllocation.created_at, ApplicationVehicleAllocation.id))).all()
    return [_dict(row) for row in rows]


async def history(session: AsyncSession, line_id: UUID) -> list[dict[str, Any]]:
    rows = (await session.scalars(sa.select(ApplicationVehicleFulfillmentHistory).where(
        ApplicationVehicleFulfillmentHistory.application_vehicle_id == line_id).order_by(
        ApplicationVehicleFulfillmentHistory.created_at.desc()))).all()
    return [_dict(row) for row in rows]


async def stock(session: AsyncSession, ids: list[UUID], *, lock: bool = False) -> list[dict[str, Any]]:
    if not ids:
        return []
    stmt = sa.select(SpecialEquipmentProduct, resolved_vehicle_owner_expression().label("stock_owner_company_id")).where(SpecialEquipmentProduct.id.in_(ids)).order_by(SpecialEquipmentProduct.id)
    if lock:
        stmt = stmt.with_for_update(of=SpecialEquipmentProduct).execution_options(populate_existing=True)
    return [{**_dict(vehicle), "stock_owner_company_id": owner} for vehicle, owner in (await session.execute(stmt)).all()]


async def has_conflicting_claim(session: AsyncSession, vehicle_id: UUID, *, line_id: UUID | None = None) -> bool:
    allocation = sa.select(ApplicationVehicleAllocation.id).where(
        ApplicationVehicleAllocation.product_id == vehicle_id,
        ApplicationVehicleAllocation.released_at.is_(None))
    if line_id is not None:
        # A fast-deal claim has no application line (NULL): ``!=`` would skip it.
        allocation = allocation.where(
            ApplicationVehicleAllocation.application_vehicle_id.is_distinct_from(line_id))
    if await session.scalar(sa.select(sa.exists(allocation))):
        return True
    return bool(await session.scalar(sa.select(sa.exists().where(
        PurchaseOrder.product_id == vehicle_id,
        PurchaseOrder.status != "cancelled"))))


async def available_stock(session: AsyncSession, *, dealer_ids: list[UUID] | None,
                          complectation_id: str | None) -> list[dict[str, Any]]:
    stmt = sa.select(SpecialEquipmentProduct).where(
        SpecialEquipmentProduct.sale_status == "available",
        SpecialEquipmentProduct.publication_status == "published",
        ~sa.exists().where(ApplicationVehicleAllocation.product_id == SpecialEquipmentProduct.id,
                         ApplicationVehicleAllocation.released_at.is_(None)),
        ~sa.exists().where(PurchaseOrder.product_id == SpecialEquipmentProduct.id, PurchaseOrder.status != "cancelled"))
    if dealer_ids is not None:
        stmt = stmt.where(resolved_vehicle_owner_expression().in_(dealer_ids))
    if complectation_id is not None:
        stmt = stmt.where(SpecialEquipmentProduct.modification_id == complectation_id)
    return [_dict(row) for row in (await session.scalars(stmt.order_by(SpecialEquipmentProduct.vin, SpecialEquipmentProduct.id).limit(500))).all()]


async def save(session: AsyncSession, *, line_id: UUID, actor_id: UUID,
               quantity: int, vehicle_ids: list[UUID], expires_at: datetime,
               comment: str | None) -> None:
    row = await session.get(ApplicationVehicle, line_id)
    assert row is not None
    previous: dict[str, Any] = {"quantity": row.quantity, "confirmed_quantity": row.confirmed_quantity,
                "version": row.fulfillment_version}
    current = await allocations(session, line_id, active_only=True)
    previous["vehicle_ids"] = [str(a["vehicle_id"]) for a in current]
    retained = {a["vehicle_id"] for a in current} & set(vehicle_ids)
    removed = {a["vehicle_id"] for a in current} - set(vehicle_ids)
    now = datetime.now(UTC)
    await session.execute(sa.update(ApplicationVehicleAllocation).where(
        ApplicationVehicleAllocation.application_vehicle_id == line_id,
        ApplicationVehicleAllocation.released_at.is_(None),
        ApplicationVehicleAllocation.product_id.in_(removed)).values(released_at=now, release_reason=comment))
    await session.flush()
    for vehicle_id in removed:
        if not await has_conflicting_claim(session, vehicle_id):
            await session.execute(sa.update(SpecialEquipmentProduct).where(SpecialEquipmentProduct.id == vehicle_id,
                SpecialEquipmentProduct.sale_status == "reserved").values(sale_status="available"))
    await session.execute(sa.update(ApplicationVehicleAllocation).where(
        ApplicationVehicleAllocation.application_vehicle_id == line_id,
        ApplicationVehicleAllocation.released_at.is_(None)).values(reserved_until=expires_at))
    for vehicle in await stock(session, list(set(vehicle_ids) - retained)):
        # Set physical state before inserting claim, whose trigger then protects it.
        await session.execute(sa.update(SpecialEquipmentProduct).where(SpecialEquipmentProduct.id == vehicle["id"]).values(sale_status="reserved"))
        session.add(ApplicationVehicleAllocation(application_vehicle_id=line_id,
            product_id=vehicle["id"], vin=vehicle["vin"],
            unit_price=Decimal(str(row.final_price or row.unit_price or 0)),
            reserved_until=expires_at, created_by=actor_id))
    active_vins = [a["vin"] for a in await allocations(session, line_id, active_only=True)]
    row.vin = active_vins[0] if len(active_vins) == 1 else None
    row.confirmed_quantity = quantity
    row.quantity = quantity
    row.fulfillment_version = ApplicationVehicle.fulfillment_version + 1
    session.add(ApplicationVehicleFulfillmentHistory(
        application_vehicle_id=line_id, actor_id=actor_id,
        previous_values=previous, new_values={
            "quantity": quantity, "confirmed_quantity": quantity,
            "vehicle_ids": [str(v) for v in vehicle_ids],
            "version": previous["version"] + 1,
        }, comment=comment))
    await session.flush()


async def release_line(session: AsyncSession, line_id: UUID, *, reason: str) -> None:
    current = await allocations(session, line_id, active_only=True)
    if not current:
        return
    await stock(session, [a["vehicle_id"] for a in current], lock=True)
    await session.execute(sa.update(ApplicationVehicleAllocation).where(
        ApplicationVehicleAllocation.application_vehicle_id == line_id,
        ApplicationVehicleAllocation.released_at.is_(None),
        ApplicationVehicleAllocation.completed_at.is_(None)).values(released_at=datetime.now(UTC), release_reason=reason))
    await session.flush()
    for allocation in current:
        alloc_vid = allocation.get("product_id") or allocation["vehicle_id"]
        if not await has_conflicting_claim(session, alloc_vid):
            await session.execute(sa.update(SpecialEquipmentProduct).where(SpecialEquipmentProduct.id == alloc_vid,
                SpecialEquipmentProduct.sale_status == "reserved").values(sale_status="available"))
    await session.execute(sa.update(ApplicationVehicle).where(ApplicationVehicle.id == line_id).values(
        vin=None, fulfillment_version=ApplicationVehicle.fulfillment_version + 1))


async def release_application(session: AsyncSession, application_id: UUID, *, reason: str) -> None:
    ids = (await session.scalars(sa.select(ApplicationVehicle.id).where(
        ApplicationVehicle.application_id == application_id).order_by(ApplicationVehicle.id))).all()
    for line_id in ids:
        await release_line(session, line_id, reason=reason)


async def has_managed_lines(session: AsyncSession, application_id: UUID) -> bool:
    return bool(await session.scalar(sa.select(sa.exists().where(
        ApplicationVehicle.application_id == application_id,
        ApplicationVehicle.fulfillment_version > 0))))


async def complete_application(session: AsyncSession, application_id: UUID) -> None:
    """A completed deal consumes its selected physical units without releasing them."""
    from domain.errors import ApplicationVehicleAssignmentError
    lines = (await session.scalars(sa.select(ApplicationVehicle).where(
        ApplicationVehicle.application_id == application_id,
        ApplicationVehicle.fulfillment_version > 0,
        ApplicationVehicle.car_status.in_(("active", "confirmed", "replacement")),
    ).order_by(ApplicationVehicle.id))).all()
    all_allocations = []
    for row in lines:
        current = await allocations(session, row.id, active_only=True)
        if len(current) != row.quantity:
            raise ApplicationVehicleAssignmentError("Для завершения сделки подберите все подтверждённые автомобили")
        all_allocations.extend(current)
    if not all_allocations:
        return
    vehicle_ids = [a["vehicle_id"] for a in all_allocations]
    await stock(session, vehicle_ids, lock=True)
    now = datetime.now(UTC)
    await session.execute(sa.update(ApplicationVehicleAllocation).where(
        ApplicationVehicleAllocation.id.in_([a["id"] for a in all_allocations]),
        ApplicationVehicleAllocation.completed_at.is_(None),
    ).values(completed_at=now))
    await session.flush()
    await session.execute(sa.update(SpecialEquipmentProduct).where(SpecialEquipmentProduct.id.in_(vehicle_ids)).values(sale_status="sold"))
    await session.flush()


async def legacy_reservations(session: AsyncSession, rows: list[dict[str, Any]]) -> dict[UUID, dict[str, Any]]:
    """Recognize old physical reservations in two batch queries without writing history."""
    candidates = [row for row in rows if row.get("vehicle_id") is not None
                  and not row.get("fulfillment_version")
                  and not (row.get("is_model_order") and not row.get("vin"))]
    if not candidates:
        return {}
    vehicle_ids = {row["vehicle_id"] for row in candidates}
    vehicles = (await session.scalars(sa.select(SpecialEquipmentProduct).where(
        SpecialEquipmentProduct.id.in_(vehicle_ids), SpecialEquipmentProduct.sale_status == "reserved",
        ~sa.exists().where(ApplicationVehicleAllocation.product_id == SpecialEquipmentProduct.id,
                         ApplicationVehicleAllocation.released_at.is_(None)),
        ~sa.exists().where(PurchaseOrder.product_id == SpecialEquipmentProduct.id, PurchaseOrder.status != "cancelled"),
    ))).all()
    reserved = {vehicle.id: vehicle for vehicle in vehicles}
    if not reserved:
        return {}
    references = (await session.execute(sa.select(ApplicationVehicle.product_id, ApplicationVehicle.id).where(
        ApplicationVehicle.product_id.in_(reserved),
        ApplicationVehicle.car_status.in_(("active", "confirmed", "replacement")),
        sa.or_(ApplicationVehicle.is_model_order.is_not(True), ApplicationVehicle.vin.is_not(None)),
    ))).all()
    owners: dict[UUID, set[UUID]] = {}
    for vehicle_id, line_id in references:
        owners.setdefault(vehicle_id, set()).add(line_id)
    result = {}
    for row in candidates:
        vehicle = reserved.get(row["vehicle_id"])
        if vehicle is None or owners.get(vehicle.id, set()) - {row["id"]}:
            continue
        result[row["id"]] = {
            "id": row["id"], "application_vehicle_id": row["id"], "vehicle_id": vehicle.id,
            "vin": vehicle.vin, "unit_price": row.get("final_price") or row.get("unit_price") or 0,
            "reserved_until": row.get("reserve_expires_at"), "released_at": None,
            "completed_at": None, "legacy": True, "created_by": row.get("vin_assigned_by"),
            "created_at": row.get("vin_assigned_at") or row.get("created_at"), "release_reason": None,
        }
    return result


async def legacy_reservation(session: AsyncSession, row: dict[str, Any]) -> dict[str, Any] | None:
    return (await legacy_reservations(session, [row])).get(row["id"])


async def adopt_legacy_reservation(session: AsyncSession, *, row: dict[str, Any], actor_id: UUID,
                                   expires_at: datetime) -> None:
    legacy = await legacy_reservation(session, row)
    if legacy is None:
        return
    session.add(ApplicationVehicleAllocation(application_vehicle_id=row["id"],
        product_id=legacy["vehicle_id"], vin=legacy["vin"], unit_price=legacy["unit_price"],
        reserved_until=expires_at, created_by=actor_id))
    await session.flush()


async def require_complete_for_financing(session: AsyncSession, application_id: UUID) -> None:
    from domain.errors import ApplicationVehicleAssignmentError
    lines = (await session.scalars(sa.select(ApplicationVehicle).where(
        ApplicationVehicle.application_id == application_id,
        ApplicationVehicle.fulfillment_version > 0,
        ApplicationVehicle.car_status.in_(("active", "confirmed", "replacement"))))).all()
    for row in lines:
        if len(await allocations(session, row.id, active_only=True)) != row.quantity:
            raise ApplicationVehicleAssignmentError("Перед передачей в ЛК подберите все подтверждённые автомобили")


async def enrich_line_composition(session: AsyncSession, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    grouped: dict[UUID, list[dict[str, Any]]] = {}
    items = (await session.scalars(sa.select(ApplicationVehicleAllocation).where(
        ApplicationVehicleAllocation.application_vehicle_id.in_([row["id"] for row in rows]),
        ApplicationVehicleAllocation.released_at.is_(None)))).all()
    for allocation in items:
        if allocation.application_vehicle_id is None:
            continue  # a fast-deal claim belongs to no application line
        grouped.setdefault(allocation.application_vehicle_id, []).append(_dict(allocation))
    legacy = await legacy_reservations(session, rows)
    for row in rows:
        active = grouped.get(row["id"], [])
        if row["id"] in legacy:
            active = [*active, legacy[row["id"]]]
        row["allocations"] = active
        row["allocated_vehicle_ids"] = [a["vehicle_id"] for a in active]
        row["allocated_vins"] = [a["vin"] for a in active]
        if row.get("fulfillment_version"):
            canonical_vin = active[0]["vin"] if len(active) == 1 else None
            row.update(vin=canonical_vin, assigned_vin=canonical_vin, vehicle_vin=canonical_vin)
