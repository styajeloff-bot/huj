"""Transactional inventory deletion; no commits or external side effects."""
from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from domain.vehicle_deletion import BLOCKING_RELATIONS, BlockingReason


async def lock_bindings(session: AsyncSession) -> None:
    """Freeze bindings before selecting the warehouse's complete candidate set."""
    await session.execute(text("LOCK TABLE special_equipment_products IN SHARE ROW EXCLUSIVE MODE"))


async def warehouse_exists(session: AsyncSession, warehouse_id: UUID) -> bool:
    return bool((await session.execute(
        text("SELECT EXISTS (SELECT 1 FROM warehouses WHERE id = :id)"),
        {"id": warehouse_id},
    )).scalar_one())


async def get_vehicles(
    session: AsyncSession,
    *,
    vehicle_id: UUID | None = None,
    warehouse_id: UUID | None = None,
    lock: bool = False,
) -> list[dict[str, Any]]:
    conditions = []
    params: dict[str, Any] = {}
    if vehicle_id is not None:
        conditions.append("p.id = :vehicle_id")
        params["vehicle_id"] = vehicle_id
    if warehouse_id is not None:
        conditions.append("p.warehouse_id = :warehouse_id")
        params["warehouse_id"] = warehouse_id
    if not conditions:
        raise ValueError("A vehicle or warehouse must be specified")
    query = """
        SELECT p.id, COALESCE(p.vin, '') AS vin, p.images,
               concat_ws(' ', m.name, cm.name, p.manufacture_year::text) AS name
        FROM special_equipment_products p
        LEFT JOIN special_equipment_models cm ON cm.id = p.model_id
        LEFT JOIN special_equipment_marks m ON m.id = cm.mark_id
        WHERE """ + " AND ".join(conditions) + " ORDER BY p.id"  # noqa: S608 -- fixed SQL; values are bound
    if lock:
        query += " FOR UPDATE OF p"
    return [dict(row) for row in (await session.execute(text(query), params)).mappings()]


async def blocking_reasons(
    session: AsyncSession, vehicle_ids: list[UUID],
) -> dict[UUID, list[BlockingReason]]:
    """One statement for all candidates and all dependencies (one snapshot)."""
    result: dict[UUID, list[BlockingReason]] = {key: [] for key in vehicle_ids}
    if not vehicle_ids:
        return result
    queries = []
    for table in BLOCKING_RELATIONS:
        if table == "calculation_history":
            queries.append("""
                SELECT 'calculation_history' AS type, refs.vehicle_id, count(*) AS count
                FROM calculation_history h
                CROSS JOIN LATERAL (
                    SELECT DISTINCT unnest(h.vehicle_ids) AS vehicle_id
                ) refs
                WHERE refs.vehicle_id = ANY(CAST(:ids AS uuid[]))
                GROUP BY refs.vehicle_id
            """)
        else:
            queries.append(
                f"SELECT '{table}' AS type, product_id AS vehicle_id, count(*) AS count "  # noqa: S608 -- fixed relation registry
                f"FROM {table} WHERE product_id = ANY(CAST(:ids AS uuid[])) GROUP BY product_id"
            )
    rows = await session.execute(text(" UNION ALL ".join(queries)), {"ids": vehicle_ids})
    for row in rows.mappings():
        result[row["vehicle_id"]].append(BlockingReason(
            type=row["type"], count=row["count"],
            description=BLOCKING_RELATIONS[row["type"]],
        ))
    return result


async def delete_checked_vehicle(
    session: AsyncSession, vehicle: dict[str, Any],
) -> dict[str, int]:
    """Caller holds locks and has checked every blocker in this transaction."""
    vehicle_id = vehicle["id"]
    transfers = await session.execute(
        text("DELETE FROM vehicle_warehouse_transfers WHERE product_id = :id RETURNING id"),
        {"id": vehicle_id},
    )
    cleaned = {
        "vehicle_warehouse_transfers": len(transfers.all()),
        "vehicle_warehouses": 0,
    }
    await session.execute(text("DELETE FROM special_equipment_products WHERE id = :id"), {"id": vehicle_id})
    return cleaned


async def unbind_warehouse(session: AsyncSession, warehouse_id: UUID) -> int:
    vehicles = await get_vehicles(session, warehouse_id=warehouse_id, lock=True)
    await ensure_unbinding_allowed(session, [vehicle["id"] for vehicle in vehicles])
    result = await session.execute(
        text("UPDATE special_equipment_products SET warehouse_id = NULL WHERE warehouse_id = :id RETURNING id"),
        {"id": warehouse_id},
    )
    return len(result.all())


async def invalidate_catalog(session: AsyncSession) -> None:
    pass


async def ensure_unbinding_allowed(session: AsyncSession, vehicle_ids: list[UUID]) -> None:
    """Caller holds physical-row locks."""
    from domain.errors import ApplicationVehicleAssignmentError
    if not vehicle_ids:
        return
    await session.execute(text("SELECT id FROM special_equipment_products WHERE id = ANY(CAST(:ids AS uuid[])) ORDER BY id FOR UPDATE"), {"ids": vehicle_ids})
    claimed = (await session.execute(text("""
        SELECT EXISTS (SELECT 1 FROM application_vehicle_allocations
        WHERE product_id = ANY(CAST(:ids AS uuid[])) AND released_at IS NULL)
    """), {"ids": vehicle_ids})).scalar_one()
    if claimed:
        raise ApplicationVehicleAssignmentError("Нельзя отвязать технику, закреплённую за заявкой, быстрой сделкой или завершённой сделкой")
