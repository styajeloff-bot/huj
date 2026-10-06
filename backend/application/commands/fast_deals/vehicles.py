"""Positions of a deal: add, change, replace and remove.

Before the DL split the leasing company may add units of any dealer; afterwards only
units of the deal's own dealer. The dealer of a DL deal may only correct the price and
the text data of manual positions. A removed or replaced position stays in the deal as
a soft state (``removed`` / ``replaced``): its VIN, prices and supports are history.
A reserved unit is released when its position leaves; the reservation of a new unit is
taken at the next send, never here.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.commands.fast_deals.editing import (
    begin_edit,
    ensure_editable,
    recalculate,
    record_and_render,
    unchanged_card,
)
from application.fast_deals import reservation
from application.fast_deals.access import DealContext, active_vehicle, load_for_mutation
from application.fast_deals.actor import Actor
from application.fast_deals.history import field_changes
from application.fast_deals.vehicle_builder import (
    added_changes,
    build_position,
    patch_columns,
    removed_changes,
    vehicle_changes,
)
from domain.fast_deals.errors import FastDealAccessDeniedError, FastDealValidationError
from domain.fast_deals.values import HistoryEvent, ItemStatus, Party
from infrastructure.repositories import fast_deal_repository as repo

Record = dict[str, Any]

_OPTION_COLUMNS = ("equipments", "services", "purposes", "regions")
# Requested terms are computed from the total of the positions: with no position left
# they mean nothing (and could not be rebased on a zero total), so they start over.
_NO_TERMS: Record = {
    "down_payment_mode": None,
    "down_payment": None,
    "down_payment_percent": None,
    "lease_term_months": None,
    "monthly_payment": None,
    "monthly_payment_is_manual": False,
    "calculated_monthly_payment": None,
    "buyout_amount": None,
    "calc_snapshot": None,
}
_LOGGED_TERMS = tuple(name for name in _NO_TERMS if name != "calc_snapshot")


@dataclass
class AddVehicleCommand:
    actor: Actor
    deal_id: UUID
    if_match: str | None
    body: dict[str, Any]


@dataclass
class PatchVehicleCommand:
    actor: Actor
    deal_id: UUID
    vehicle_id: UUID
    if_match: str | None
    body: dict[str, Any]


@dataclass
class RemoveVehicleCommand:
    actor: Actor
    deal_id: UUID
    vehicle_id: UUID
    if_match: str | None


def _find(vehicles: list[Record], vehicle_id: UUID) -> Record:
    return next(item for item in vehicles if item["id"] == vehicle_id)


async def handle_add_vehicle(cmd: AddVehicleCommand, session: AsyncSession) -> dict[str, Any]:
    """Add one unit: a catalog listing or a manual position; the server derives the rest."""
    ctx = await load_for_mutation(session, cmd.actor, cmd.deal_id, cmd.if_match)
    ensure_editable(ctx)
    values = await build_position(
        session,
        ctx.deal,
        cmd.body,
        created_by=cmd.actor.user_id,
        existing=ctx.vehicles,
        position=await repo.next_vehicle_position(session, ctx.deal_id),
    )
    scope = await begin_edit(session, ctx)
    row = await repo.insert_vehicle(session, values)
    _, vehicles = await recalculate(session, scope)
    return await record_and_render(
        session, scope, HistoryEvent.VEHICLE_ADDED,
        changes=added_changes(_find(vehicles, row["id"])),
    )


async def handle_patch_vehicle(cmd: PatchVehicleCommand, session: AsyncSession) -> dict[str, Any]:
    """Change allowed fields of a position, or replace it with another unit."""
    ctx = await load_for_mutation(session, cmd.actor, cmd.deal_id, cmd.if_match)
    ensure_editable(ctx, dealer_allowed=True)
    vehicle = active_vehicle(ctx, cmd.vehicle_id)
    replace_with = cmd.body.get("replace_with")
    fields = {name: value for name, value in cmd.body.items() if name != "replace_with"}
    if replace_with is not None:
        if any(value is not None for value in fields.values()):
            raise FastDealValidationError(
                "Замену нельзя сочетать с изменением полей", field="replace_with"
            )
        return await _replace_vehicle(session, ctx, vehicle, replace_with)
    if not fields:
        raise FastDealValidationError("Не указано, что изменить")
    updates = await patch_columns(
        session,
        deal=ctx.deal,
        vehicle=vehicle,
        fields=fields,
        party=ctx.party,
        existing=ctx.vehicles,
    )
    if not updates:
        # A repeated save must not reset a deal under review.
        return await unchanged_card(session, ctx)
    scope = await begin_edit(session, ctx, dealer_allowed=True)
    await repo.update_vehicle(session, vehicle["id"], updates)
    _, vehicles = await recalculate(session, scope)
    return await record_and_render(
        session, scope, HistoryEvent.VEHICLE_CHANGED,
        changes=vehicle_changes(vehicle, _find(vehicles, vehicle["id"])),
    )


async def _replace_vehicle(
    session: AsyncSession, ctx: DealContext, vehicle: Record, replace_with: dict[str, Any]
) -> dict[str, Any]:
    """The old position becomes ``replaced``; the new one takes its place in the order.

    Options, purposes and regions stay with the place; the price adjustment and the
    supports belong to the replaced unit and do not move to the new one.
    """
    if ctx.party == Party.DEALER:
        raise FastDealAccessDeniedError("Заменить позицию может только инициатор сделки")
    values = await build_position(
        session,
        ctx.deal,
        replace_with,
        created_by=ctx.actor.user_id,
        existing=[item for item in ctx.vehicles if item["id"] != vehicle["id"]],
        position=vehicle["position"],
    )
    scope = await begin_edit(session, ctx)
    await reservation.release_vehicle(session, vehicle["id"], reason="Позиция заменена")
    # The old position leaves the active set first: the unit may be chosen again.
    await repo.update_vehicle(session, vehicle["id"], {"item_status": ItemStatus.REPLACED.value})
    row = await repo.insert_vehicle(
        session, {**values, **{name: vehicle[name] for name in _OPTION_COLUMNS}}
    )
    await repo.update_vehicle(session, vehicle["id"], {"replaced_by_id": row["id"]})
    _, vehicles = await recalculate(session, scope)
    changes = {
        **removed_changes(vehicle, ItemStatus.REPLACED.value),
        f"vehicle.{vehicle['id']}.replaced_by_id": {"before": None, "after": str(row["id"])},
        **added_changes(_find(vehicles, row["id"])),
    }
    return await record_and_render(
        session, scope, HistoryEvent.VEHICLE_REPLACED, changes=changes
    )


async def handle_remove_vehicle(
    cmd: RemoveVehicleCommand, session: AsyncSession
) -> dict[str, Any]:
    """Soft removal: the position stays as history, its reservation is released."""
    ctx = await load_for_mutation(session, cmd.actor, cmd.deal_id, cmd.if_match)
    ensure_editable(ctx)
    vehicle = active_vehicle(ctx, cmd.vehicle_id)
    scope = await begin_edit(session, ctx)
    await reservation.release_vehicle(session, vehicle["id"], reason="Позиция удалена из сделки")
    await repo.update_vehicle(session, vehicle["id"], {"item_status": ItemStatus.REMOVED.value})
    changes = removed_changes(vehicle, ItemStatus.REMOVED.value)
    if len(ctx.vehicles) == 1:
        cleared = await repo.update_deal(session, scope.deal["id"], _NO_TERMS)
        changes.update(field_changes(scope.deal, cleared, _LOGGED_TERMS))
    await recalculate(session, scope)
    return await record_and_render(
        session, scope, HistoryEvent.VEHICLE_REMOVED, changes=changes
    )
