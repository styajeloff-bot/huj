"""Discount or markup of one position (never both, ``null`` clears it)."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
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
from application.fast_deals.access import DealContext, active_vehicle, load_for_mutation
from application.fast_deals.actor import Actor
from application.fast_deals.pricing import priced_columns
from application.fast_deals.vehicle_builder import vehicle_changes
from domain.fast_deals import pricing
from domain.fast_deals.errors import FastDealValidationError
from domain.fast_deals.values import AdjustmentType, HistoryEvent
from infrastructure.repositories import fast_deal_repository as repo

Record = dict[str, Any]

_ADJUSTMENT_FIELDS = ("adjustment_type", "adjustment_amount", "final_price")


@dataclass
class PriceAdjustmentCommand:
    actor: Actor
    deal_id: UUID
    vehicle_id: UUID
    if_match: str | None
    adjustment_type: str | None
    amount: Decimal | None


def _allowed_types(ctx: DealContext) -> tuple[AdjustmentType, ...]:
    """The dealer of a DD may give a discount; in a DL a discount or a markup.

    In a DL both the dealer (its change goes to the leasing company) and the leasing
    company (correcting a refused deal) work with the same two kinds.
    """
    if ctx.is_dd:
        return (AdjustmentType.DISCOUNT,)
    return (AdjustmentType.DISCOUNT, AdjustmentType.MARKUP)


async def handle_price_adjustment(
    cmd: PriceAdjustmentCommand, session: AsyncSession
) -> dict[str, Any]:
    """Set or clear the adjustment; the final price is recomputed on the server."""
    ctx = await load_for_mutation(session, cmd.actor, cmd.deal_id, cmd.if_match)
    ensure_editable(ctx, dealer_allowed=True)
    vehicle = active_vehicle(ctx, cmd.vehicle_id)
    kind, amount = pricing.validate_adjustment(
        cmd.adjustment_type, cmd.amount, allowed=_allowed_types(ctx)
    )
    adjustment_type = kind.value if kind is not None else None
    if vehicle["adjustment_type"] == adjustment_type and vehicle["adjustment_amount"] == amount:
        return await unchanged_card(session, ctx)
    _ensure_price_stays_valid(vehicle, adjustment_type, amount)
    scope = await begin_edit(session, ctx, dealer_allowed=True)
    await repo.update_vehicle(
        session, vehicle["id"],
        {"adjustment_type": adjustment_type, "adjustment_amount": amount},
    )
    _, vehicles = await recalculate(session, scope)
    after = next(item for item in vehicles if item["id"] == vehicle["id"])
    return await record_and_render(
        session, scope, HistoryEvent.VEHICLE_CHANGED,
        changes=vehicle_changes(vehicle, after, _ADJUSTMENT_FIELDS),
    )


def _ensure_price_stays_valid(
    vehicle: Record, adjustment_type: str | None, amount: Decimal | None
) -> None:
    """Report a price below zero at the amount field, not at a generic price field."""
    candidate = {**vehicle, "adjustment_type": adjustment_type, "adjustment_amount": amount}
    try:
        priced_columns(candidate, vehicle["support_amount"])
    except FastDealValidationError as exc:
        raise FastDealValidationError(str(exc), field="amount") from exc
