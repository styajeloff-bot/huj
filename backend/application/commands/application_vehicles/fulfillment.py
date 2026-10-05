"""Supplier fulfillment: quantities and a replaceable exclusive set of physical units."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.commands.application_vehicles.dealer_action import (
    DealerVehicleActionCommand,
    _ensure_vehicle_scope,
)
from application.dealer_distribution_access import ensure_whole_vehicle_write_allowed
from application.distributor_scope import resolve_distributor_application_dealer_filter
from application.errors import ServiceError
from application.notifications.leasing_events import reservation_expiry_timestamp
from domain.dealer_distribution_access import ensure_distributed_quantity_retained
from domain.vehicle_fulfillment import (
    ensure_fulfillment_request,
    ensure_stock_matches,
    fulfillment_editable,
)
from infrastructure.repositories import application_repository as applications
from infrastructure.repositories import vehicle_fulfillment_repository as repo


@dataclass
class FulfillmentCommand:
    application_vehicle_id: UUID
    actor_id: UUID
    actor_role: str
    actor_company_id: UUID | None
    actor_leasing_company_id: UUID | None = None
    version: int = 0
    confirmed_quantity: int = 1
    vehicle_ids: list[UUID] = field(default_factory=list)
    reserve_expires_at: date | None = None
    comment: str | None = None


async def _scope(cmd: FulfillmentCommand, session: AsyncSession) -> list[UUID] | None:
    if cmd.actor_role not in {"dealer", "distributor", "carcraft_employee"}:
        raise ServiceError("Подбор доступен поставщику и администратору", 403)
    await _ensure_vehicle_scope(DealerVehicleActionCommand(
        application_vehicle_id=cmd.application_vehicle_id, actor_id=cmd.actor_id,
        actor_role=cmd.actor_role, actor_company_id=cmd.actor_company_id, action="reserve"), session)
    if cmd.actor_role == "dealer":
        return [cmd.actor_company_id] if cmd.actor_company_id else []
    return await resolve_distributor_application_dealer_filter(session, actor_id=cmd.actor_id,
        actor_role=cmd.actor_role, company_id=cmd.actor_company_id)


async def _context(cmd: FulfillmentCommand, session: AsyncSession, *, lock: bool = False) -> tuple[dict[str, Any], list[UUID] | None, bool]:
    row = await repo.line(session, cmd.application_vehicle_id, lock=lock)
    if row is None:
        raise ServiceError("Позиция заявки не найдена", 404)
    if cmd.actor_role in {"dealer", "distributor", "carcraft_employee"}:
        dealer_ids = await _scope(cmd, session)
        await ensure_whole_vehicle_write_allowed(session,
            application_vehicle_id=cmd.application_vehicle_id,
            actor_role=cmd.actor_role, actor_company_id=cmd.actor_company_id, lock=lock)
    elif not lock and cmd.actor_role in {"client", "leasing_company"}:
        from application.queries.applications.get_application import (
            ApplicationAccessQuery,
            get_authorized_application,
        )
        await get_authorized_application(ApplicationAccessQuery(
            application_id=row["application_id"], actor_id=cmd.actor_id, actor_role=cmd.actor_role,
            actor_company_id=cmd.actor_company_id, actor_leasing_company_id=cmd.actor_leasing_company_id), session)
        dealer_ids = []
    else:
        raise ServiceError("Подбор доступен поставщику и администратору", 403)
    app = await applications.get_by_id(session, row["application_id"])
    editable = fulfillment_editable(actor_role=cmd.actor_role,
        application_status=app.get("status") if app else None, line_status=row.get("car_status"),
        has_lc_children=await applications.has_lc_children(session, row["application_id"]))
    return row, dealer_ids, editable


async def get_fulfillment(cmd: FulfillmentCommand, session: AsyncSession) -> dict[str, Any]:
    row, dealer_ids, editable = await _context(cmd, session)
    allocated = await repo.allocations(session, cmd.application_vehicle_id)
    reservation_fixed = await applications.has_lc_children(session, row["application_id"])
    for allocation in allocated:
        allocation["reservation_fixed"] = reservation_fixed
    legacy = await repo.legacy_reservation(session, row)
    if legacy is not None:
        allocated.append(legacy)
    active = [item for item in allocated if item["released_at"] is None]
    concrete = await repo.stock(session, [row["vehicle_id"]] if row.get("vehicle_id") else [])
    complectation = row.get("modification_id") or (concrete[0].get("complectation_id") if concrete else None)
    available = await repo.available_stock(session, dealer_ids=dealer_ids, complectation_id=complectation)
    retained = await repo.stock(session, [item["vehicle_id"] for item in active]) if dealer_ids != [] else []
    public_stock_keys = ("id", "vin", "base_price", "discount_price", "mark_id", "model_id", "complectation_id", "color", "year", "status")
    quantity = int(row.get("quantity") or 1)
    from application.queries.applications.get_application import (
        GetApplicationQuery,
        handle_get_application,
    )
    application = await handle_get_application(GetApplicationQuery(
        application_id=row["application_id"], actor_id=cmd.actor_id, actor_role=cmd.actor_role,
        actor_company_id=cmd.actor_company_id, actor_leasing_company_id=cmd.actor_leasing_company_id), session)
    return {
        "application_vehicle_id": cmd.application_vehicle_id,
        "requested_quantity": row.get("requested_quantity"),
        "confirmed_quantity": row.get("confirmed_quantity"),
        "quantity": quantity, "version": row["fulfillment_version"], "editable": editable,
        "reservation_fixed": reservation_fixed,
        "allocated_quantity": len(active), "remaining_quantity": max(0, quantity - len(active)),
        "allocations": allocated, "available_vehicles": [{key: vehicle.get(key) for key in public_stock_keys} for vehicle in [*retained, *available]],
        "history": await repo.history(session, cmd.application_vehicle_id),
        "calculation": application.get("calculation") or {},
        "application_totals": {key: application.get(key) for key in (
            "total_amount", "down_payment", "monthly_payment", "total_cost", "total_interest",
            "buyout_amount", "vat_refund", "profit_tax_savings", "total_savings")},
    }


async def save_fulfillment(cmd: FulfillmentCommand, session: AsyncSession) -> dict[str, Any]:
    row, dealer_ids, editable = await _context(cmd, session, lock=True)
    if not editable:
        raise ServiceError("После передачи в лизинговую компанию состав заявки менять нельзя", 409)
    if row["fulfillment_version"] != cmd.version:
        raise ServiceError("Подбор уже изменён. Обновите заявку и повторите действие", 409)
    distribution_scope = await ensure_whole_vehicle_write_allowed(session,
        application_vehicle_id=cmd.application_vehicle_id,
        actor_role=cmd.actor_role, actor_company_id=cmd.actor_company_id)
    ensure_distributed_quantity_retained(
        distributed_quantity=distribution_scope["distributed_quantity"], quantity=cmd.confirmed_quantity)
    current = await repo.allocations(session, cmd.application_vehicle_id, active_only=True)
    legacy = await repo.legacy_reservation(session, row)
    if legacy is not None:
        current.append(legacy)
    current_ids = {item["vehicle_id"] for item in current}
    ensure_fulfillment_request(quantity=cmd.confirmed_quantity, vehicle_ids=cmd.vehicle_ids,
        expires=cmd.reserve_expires_at, today=datetime.now(UTC).date(), current_ids=current_ids, comment=cmd.comment)
    vehicles = await repo.stock(session, sorted(current_ids | set(cmd.vehicle_ids)), lock=True)
    selected = {v["id"]: v for v in vehicles}
    concrete = await repo.stock(session, [row["vehicle_id"]] if row.get("vehicle_id") else [])
    complectation = row.get("modification_id") or (concrete[0].get("complectation_id") if concrete else None)
    for vehicle_id in cmd.vehicle_ids:
        vehicle = selected.get(vehicle_id)
        if not vehicle or (dealer_ids is not None and vehicle["stock_owner_company_id"] not in dealer_ids):
            raise ServiceError("Машина отсутствует на доступном складе", 404)
        ensure_stock_matches(vehicle=vehicle, retained=vehicle_id in current_ids, complectation_id=complectation)
        if await repo.has_conflicting_claim(session, vehicle_id, line_id=cmd.application_vehicle_id):
            raise ServiceError("Машина уже закреплена за другой заявкой или покупкой", 409)
    expires_at = reservation_expiry_timestamp(cmd.reserve_expires_at)
    assert expires_at is not None
    await repo.adopt_legacy_reservation(session, row=row, actor_id=cmd.actor_id, expires_at=expires_at)
    await repo.save(session, line_id=cmd.application_vehicle_id, actor_id=cmd.actor_id,
        quantity=cmd.confirmed_quantity, vehicle_ids=cmd.vehicle_ids,
        expires_at=expires_at, comment=cmd.comment)
    from application.commands.application_vehicles.recalculate_quantity import (
        recalculate_quantity,
    )
    await recalculate_quantity(session, application_vehicle_id=cmd.application_vehicle_id,
                               previous_quantity=int(row.get("quantity") or 1))
    from application.notifications.leasing_events import record_leasing_event
    application = await applications.get_by_id(session, row["application_id"])
    assert application is not None
    await record_leasing_event(session, application=application,
        event_type="leasing.vehicle_reserved", actor_user_id=cmd.actor_id,
        previous_values={"quantity": row["quantity"], "vehicle_ids": sorted(str(v) for v in current_ids)},
        new_values={"quantity": cmd.confirmed_quantity, "vehicle_ids": sorted(str(v) for v in cmd.vehicle_ids)},
        payload={"application_vehicle_id": cmd.application_vehicle_id, "comment": cmd.comment},
        occurrence_key=f"fulfillment:{cmd.application_vehicle_id}:{cmd.version + 1}")
    return await get_fulfillment(cmd, session)


async def fulfillment_event_snapshot(cmd: FulfillmentCommand, session: AsyncSession) -> dict[str, Any]:
    """Build before commit; caller publishes only after the transaction succeeds."""
    row = await repo.line(session, cmd.application_vehicle_id)
    assert row is not None
    records = await repo.allocations(session, cmd.application_vehicle_id)
    from infrastructure.messaging.dwh_events import serialise_dwh_value
    snapshot = serialise_dwh_value({"line": row, "application": await applications.get_by_id(session, row["application_id"]),
            "vehicles": await repo.stock(session, list({a["vehicle_id"] for a in records}))})
    assert isinstance(snapshot, dict)
    return snapshot


def publish_fulfillment_snapshot(snapshot: dict[str, Any]) -> None:
    from infrastructure.messaging.dwh_events import (
        emit_app_vehicle_changed,
        emit_leasing_application_changed,
        emit_vehicle_changed,
    )
    emit_app_vehicle_changed({**snapshot["line"], "_deleted": False})
    if snapshot["application"]:
        app = snapshot["application"]
        emit_leasing_application_changed({**app, "application_id": app["id"], "_deleted": False})
    for vehicle in snapshot["vehicles"]:
        emit_vehicle_changed({**vehicle, "_deleted": False})
