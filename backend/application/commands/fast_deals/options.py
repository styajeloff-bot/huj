"""Options of one position: equipment, services, purposes and regions.

The request carries the complete set: it replaces the previous one atomically, and the
audit entry keeps what was there before, so removed values stay readable in history.
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
from application.fast_deals.access import active_vehicle, load_for_mutation
from application.fast_deals.actor import Actor
from application.fast_deals.vehicle_builder import normalize_options, vehicle_changes
from domain.fast_deals.values import HistoryEvent
from infrastructure.repositories import fast_deal_repository as repo

_LOGGED_FIELDS = ("equipments", "services", "purposes", "regions", "final_price")


@dataclass
class SetOptionsCommand:
    actor: Actor
    deal_id: UUID
    vehicle_id: UUID
    if_match: str | None
    equipments: list[dict[str, Any]]
    services: list[dict[str, Any]]
    purposes: list[str]
    regions: list[str]


async def handle_set_options(cmd: SetOptionsCommand, session: AsyncSession) -> dict[str, Any]:
    """Validate against the dictionaries, replace the option set, reprice the position."""
    ctx = await load_for_mutation(session, cmd.actor, cmd.deal_id, cmd.if_match)
    ensure_editable(ctx)
    vehicle = active_vehicle(ctx, cmd.vehicle_id)
    columns = await normalize_options(
        session,
        equipments=cmd.equipments,
        services=cmd.services,
        purposes=cmd.purposes,
        regions=cmd.regions,
    )
    if all(vehicle[name] == value for name, value in columns.items()):
        # A repeated save must not reset a deal under review.
        return await unchanged_card(session, ctx)
    scope = await begin_edit(session, ctx)
    await repo.update_vehicle(session, vehicle["id"], columns)
    _, vehicles = await recalculate(session, scope)
    after = next(item for item in vehicles if item["id"] == vehicle["id"])
    return await record_and_render(
        session, scope, HistoryEvent.VEHICLE_CHANGED,
        changes=vehicle_changes(vehicle, after, _LOGGED_FIELDS),
    )
