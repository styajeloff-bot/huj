
"""Unified VIN assignment on an application_vehicles row.

Phase 13 R13c — this single command replaces three legacy paths:

* ``POST /applications/vehicle/:id/assign-vin`` — self-owner (client / dealer).
* ``PATCH /admin/application-vehicles/:id/vin`` — carcraft employee.
* ``POST /distributor/model-orders/:id/assign-vin`` — distributor (model-order
  direct VIN write, scoped to the distributor's dealer ids).

Dispatch happens by ``actor_role``:

* ``carcraft_employee`` → admin path. Accepts ``vin`` or ``vehicle_id``.
  If a ``vehicle_id`` is passed we copy the VIN from the existing vehicle
  and move it into ``reserved`` (same behaviour as the legacy admin
  handler).
* ``distributor`` → distributor path. Requires a ``vin`` string. The row
  must live under the distributor's dealer scope (filtered via
  ``DistributorScope.dealer_filter()``). No ``vehicle_id`` fan-out.
* ``client`` / ``dealer`` / ``leasing_company`` → self-owner path. The
  parent application must be ``approved`` and owned by the actor. Only
  ``vehicle_id`` is supported here (we copy the VIN from the picked
  vehicle and reserve it).

All paths enforce the global VIN uniqueness guard across
``application_vehicles`` and raise ``DomainError`` subclasses for any
violation (mapped to HTTP codes by ``application.errors.domain_to_http``).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.common import _isoformat
from application.dealer_distribution_access import ensure_whole_vehicle_write_allowed
from application.distributor_scope import resolve_distributor_scope
from application.permissions import ensure_application_vehicle_action_allowed
from domain.entities.vehicle import Vehicle
from domain.errors import (
    ApplicationNotFoundError,
    ApplicationVehicleAssignmentError,
    ApplicationVehicleNotFoundError,
    InvalidVehicleError,
    VehicleNotFoundError,
    VinAlreadyAssignedError,
)
from infrastructure.repositories import (
    application_repository as app_repo,
)
from infrastructure.repositories import (
    application_vehicle_repository as av_repo,
)
from infrastructure.repositories import (
    distributor_repository as distributor_repo,
)
from infrastructure.repositories import (
    special_equipment_commerce_repository as sec_repo,
)


@dataclass
class AssignVinCommand:
    """Unified VIN-assign command — role dispatch inside the handler."""

    application_vehicle_id: UUID
    actor_id: UUID
    actor_role: str
    actor_company_id: UUID | None = None
    actor_leasing_company_id: UUID | None = None
    vin: str | None = None
    vehicle_id: UUID | None = None


async def handle_assign_vin(
    cmd: AssignVinCommand, session: AsyncSession
) -> dict[str, Any]:
    """Assign a VIN to an application_vehicles row, role-dispatched.

    Returns a dict with at least ``success`` and ``message``. Admin/self-
    owner paths also include ``vin``/``assigned_vin``; the distributor
    path includes the updated ``order`` payload.
    """
    from infrastructure.repositories import (
        vehicle_fulfillment_repository as fulfillment,
    )
    await fulfillment.line(session, cmd.application_vehicle_id, lock=True)
    await ensure_whole_vehicle_write_allowed(session,
        application_vehicle_id=cmd.application_vehicle_id,
        actor_role=cmd.actor_role, actor_company_id=cmd.actor_company_id)
    if await fulfillment.allocations(session, cmd.application_vehicle_id, active_only=True):
        raise ApplicationVehicleAssignmentError("Используйте подбор автомобилей для изменения VIN")
    if cmd.vehicle_id is not None:
        await fulfillment.stock(session, [cmd.vehicle_id], lock=True)
        if await fulfillment.has_conflicting_claim(session, cmd.vehicle_id):
            raise ApplicationVehicleAssignmentError("Машина уже закреплена за заявкой или покупкой")
    if cmd.actor_role == "carcraft_employee":
        return await _handle_admin(cmd, session)
    if cmd.actor_role == "distributor":
        return await _handle_distributor(cmd, session)
    if cmd.actor_role in {"client", "dealer", "leasing_company"}:
        return await _handle_self_owner(cmd, session)
    raise ApplicationVehicleAssignmentError(
        "Роль не имеет права назначать VIN"
    )


async def _handle_admin(
    cmd: AssignVinCommand, session: AsyncSession
) -> dict[str, Any]:
    av = await av_repo.get_by_id(session, cmd.application_vehicle_id)
    if av is None:
        raise ApplicationVehicleNotFoundError(cmd.application_vehicle_id)

    if cmd.vehicle_id is not None:
        vehicle_dict = await sec_repo.get_product(session, cmd.vehicle_id)
        if vehicle_dict is None:
            raise VehicleNotFoundError(cmd.vehicle_id)
        if "status" not in vehicle_dict and "sale_status" in vehicle_dict:
            vehicle_dict["status"] = vehicle_dict["sale_status"]
        entity = Vehicle.from_dict(vehicle_dict)
        entity.ensure_can_assign_vin()

        target_vin = entity.vin
        if target_vin is None or not str(target_vin).strip():
            raise ApplicationVehicleAssignmentError(
                "У выбранного автомобиля отсутствует VIN"
            )
        if await av_repo.vin_used_on_other(
            session, vin=target_vin, exclude_id=cmd.application_vehicle_id
        ):
            raise VinAlreadyAssignedError(target_vin)

        await av_repo.update_vehicle_ref(
            session,
            cmd.application_vehicle_id,
            vehicle_id=cmd.vehicle_id,
            vin=target_vin,
            assigned_by=cmd.actor_id,
        )
        await sec_repo.update_product_sale_status(
            session, cmd.vehicle_id, "reserved"
        )
        from infrastructure.messaging.dwh_events import emit_app_vehicle_changed
        emit_app_vehicle_changed({
            "id": cmd.application_vehicle_id,
            "application_id": av.get("application_id"),
            "vehicle_id": cmd.vehicle_id,
            "modification_id": av.get("modification_id"),
            "quantity": av.get("quantity"),
            "unit_price": str(av.get("unit_price")) if av.get("unit_price") else None,
            "total_price": str(av.get("total_price")) if av.get("total_price") else None,
            "comment": av.get("comment"),
            "vin": target_vin,
            "vin_assigned_by": cmd.actor_id,
            "vin_assigned_at": None,
            "is_model_order": 1 if av.get("is_model_order") else 0,
            "created_at": _isoformat(av.get("created_at")),
            "updated_at": None,
            "_deleted": False,
        })
        return {
            "success": True,
            "message": "VIN назначен из существующего автомобиля",
            "vin": target_vin,
        }

    if cmd.vin is None:
        raise ApplicationVehicleAssignmentError(
            "Необходимо указать VIN или vehicle_id"
        )
    new_vin = cmd.vin.strip() or None
    if new_vin and await av_repo.vin_used_on_other(
        session, vin=new_vin, exclude_id=cmd.application_vehicle_id
    ):
        raise VinAlreadyAssignedError(new_vin)
    await av_repo.update_vin(
        session,
        cmd.application_vehicle_id,
        vin=new_vin,
        assigned_by=cmd.actor_id,
    )
    from infrastructure.messaging.dwh_events import emit_app_vehicle_changed
    emit_app_vehicle_changed({
        "id": cmd.application_vehicle_id,
        "application_id": av.get("application_id"),
        "vehicle_id": av.get("vehicle_id"),
        "modification_id": av.get("modification_id"),
        "quantity": av.get("quantity"),
        "unit_price": str(av.get("unit_price")) if av.get("unit_price") else None,
        "total_price": str(av.get("total_price")) if av.get("total_price") else None,
        "comment": av.get("comment"),
        "vin": new_vin,
        "vin_assigned_by": cmd.actor_id,
        "vin_assigned_at": None,
        "is_model_order": 1 if av.get("is_model_order") else 0,
        "created_at": _isoformat(av.get("created_at")),
        "updated_at": None,
        "_deleted": False,
    })
    return {
        "success": True,
        "message": "VIN обновлён" if new_vin else "VIN удалён",
        "vin": new_vin,
    }


async def _handle_distributor(
    cmd: AssignVinCommand, session: AsyncSession
) -> dict[str, Any]:
    scope = await resolve_distributor_scope(
        session,
        actor_id=cmd.actor_id, actor_role=cmd.actor_role, company_id=cmd.actor_company_id
    )
    vin = (cmd.vin or "").strip()
    if len(vin) < 10:
        raise InvalidVehicleError(
            "VIN должен содержать минимум 10 символов"
        )
    if await av_repo.vin_used_on_other(
        session, vin=vin, exclude_id=cmd.application_vehicle_id
    ):
        raise VinAlreadyAssignedError(vin)
    result = await distributor_repo.assign_vin_to_model_order(
        session,
        application_vehicle_id=cmd.application_vehicle_id,
        dealer_filter=scope.dealer_filter(),
        vin=vin,
        assigned_by=cmd.actor_id,
    )
    if result is None:
        raise ApplicationVehicleNotFoundError(cmd.application_vehicle_id)
    from infrastructure.messaging.dwh_events import emit_app_vehicle_changed
    emit_app_vehicle_changed({
        "id": cmd.application_vehicle_id,
        "application_id": result.get("application_id"),
        "vehicle_id": result.get("vehicle_id"),
        "modification_id": result.get("modification_id"),
        "quantity": result.get("quantity"),
        "unit_price": str(result.get("unit_price")) if result.get("unit_price") else None,
        "total_price": str(result.get("total_price")) if result.get("total_price") else None,
        "comment": result.get("comment"),
        "vin": vin,
        "vin_assigned_by": cmd.actor_id,
        "vin_assigned_at": None,
        "is_model_order": 1 if result.get("is_model_order") else 0,
        "created_at": _isoformat(result.get("created_at")),
        "updated_at": None,
        "_deleted": False,
    })
    return {
        "success": True,
        "message": "VIN присвоен",
        "order": result,
        "vin": vin,
    }


async def _handle_self_owner(
    cmd: AssignVinCommand, session: AsyncSession
) -> dict[str, Any]:
    av = await app_repo.get_application_vehicle(
        session, cmd.application_vehicle_id
    )
    if av is None:
        raise ApplicationVehicleNotFoundError(cmd.application_vehicle_id)

    app_dict = await app_repo.get_by_id(session, av["application_id"])
    if app_dict is None:
        raise ApplicationNotFoundError(av["application_id"])
    app = await ensure_application_vehicle_action_allowed(
        session,
        application=app_dict,
        application_vehicle_id=cmd.application_vehicle_id,
        user_id=cmd.actor_id,
        actor_role=cmd.actor_role,
        actor_company_id=cmd.actor_company_id,
        actor_leasing_company_id=cmd.actor_leasing_company_id,
    )
    app.ensure_can_assign_vin()

    if cmd.vehicle_id is None:
        raise ApplicationVehicleAssignmentError(
            "Необходимо указать vehicle_id"
        )
    vehicle_dict = await app_repo.get_vehicle(session, cmd.vehicle_id)
    if vehicle_dict is None:
        raise VehicleNotFoundError(cmd.vehicle_id)
    vehicle = Vehicle.from_dict(vehicle_dict)
    vehicle.ensure_can_assign_vin()
    vin = vehicle.vin
    if not vin:
        raise ApplicationVehicleAssignmentError(
            "У выбранного автомобиля отсутствует VIN"
        )

    if await av_repo.vin_used_on_other(
        session, vin=vin, exclude_id=cmd.application_vehicle_id
    ):
        raise VinAlreadyAssignedError(vin)

    await app_repo.assign_vin_to_application_vehicle(
        session,
        cmd.application_vehicle_id,
        vehicle_id=cmd.vehicle_id,
        vin=vin,
        assigned_by=cmd.actor_id,
    )
    await app_repo.update_vehicle_status(
        session, cmd.vehicle_id, status="reserved"
    )
    from infrastructure.messaging.dwh_events import emit_app_vehicle_changed
    from infrastructure.messaging.status_events import emit_vehicle_status_changed
    emit_vehicle_status_changed(
        vehicle_id=cmd.vehicle_id,
        old_status="available",
        new_status="reserved",
        changed_by=cmd.actor_id,
    )
    emit_app_vehicle_changed({
        "id": cmd.application_vehicle_id,
        "application_id": av.get("application_id"),
        "vehicle_id": cmd.vehicle_id,
        "modification_id": av.get("modification_id"),
        "quantity": av.get("quantity"),
        "unit_price": str(av.get("unit_price")) if av.get("unit_price") else None,
        "total_price": str(av.get("total_price")) if av.get("total_price") else None,
        "comment": av.get("comment"),
        "vin": vin,
        "vin_assigned_by": cmd.actor_id,
        "vin_assigned_at": None,
        "is_model_order": 1 if av.get("is_model_order") else 0,
        "created_at": _isoformat(av.get("created_at")),
        "updated_at": None,
        "_deleted": False,
    })
    return {
        "success": True,
        "message": "VIN успешно назначен",
        "application_vehicle_id": cmd.application_vehicle_id,
        "assigned_vin": vin,
        "vin": vin,
    }
