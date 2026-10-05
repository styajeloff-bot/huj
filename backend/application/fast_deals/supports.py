"""Compensations of the supports applied to a fast deal (created once, at confirmation).

Applied programs are snapshots in ``application_applied_supports``; at confirmation
each of them gets the compensations its program prescribes, with the source
``fast_deal``. A support request to a distributor is a price instrument only and
never produces a payout.
"""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from application.commands.compensations import (
    CreateCompensationCommand,
    handle_create_compensation,
)
from application.fast_deals.actor import Actor
from domain.fast_deals.money import ZERO, money
from infrastructure.repositories import compensation_repository as comp_repo
from infrastructure.repositories import fast_deal_repository as repo
from infrastructure.repositories import fast_deal_support_repository as support_repo

logger = logging.getLogger("carcraft-backend")

Record = dict[str, Any]

# Catalog bases that live in the position's snapshot (the unit as it was when added).
_SNAPSHOT_BASES = {"base_price": "price", "special_price": "special_price"}


async def create_compensations_on_confirm(
    session: AsyncSession, deal: Record, actor: Actor
) -> None:
    """Create compensations of the deal's applied programs once, at confirmation.

    Compensations use source ``fast_deal`` through the existing applied-support and
    compensation mechanism. A repeated call creates nothing new: a support that
    already has compensations is skipped. Removed and replaced positions get none.
    """
    deal_id = deal["id"]
    applied = await support_repo.list_applied_supports(session, deal_id)
    if not applied:
        return
    vehicles = {item["id"]: item for item in await repo.list_vehicles(session, deal_id)}
    total: Decimal = deal.get("confirmed_amount") or money(
        sum((item["final_price"] for item in vehicles.values()), ZERO)
    )
    for support in applied:
        vehicle = vehicles.get(support["fast_deal_vehicle_id"])
        program_id = support["support_program_id"]
        if vehicle is None or program_id is None:
            continue
        if await comp_repo.count_compensations_for_support(session, support["id"]):
            continue
        templates = await comp_repo.list_compensation_templates(session, program_id)
        context: dict[str, Decimal | None] | None = None
        for template in templates:
            base = template["calculation_base"]
            if base == "dealer_cost" and context is None:
                context = await comp_repo.get_calculation_context(
                    session,
                    applied_support_id=support["id"],
                    application_id=None,
                    vehicle_id=vehicle["product_id"],
                )
            base_amount = _base_amount(
                base, support=support, vehicle=vehicle, deal=deal, total=total, context=context
            )
            if base_amount <= 0:
                # A zero base (a deal of zero amount, an advance of nothing) has no payout to
                # calculate, and it must not undo a confirmation that is valid by itself.
                logger.warning(
                    "fast_deal_compensation_skipped_zero_base deal_id=%s applied_support_id=%s base=%s",
                    deal_id, support["id"], base,
                )
                continue
            await handle_create_compensation(
                CreateCompensationCommand(
                    applied_support_id=support["id"],
                    application_id=None,
                    fast_deal_id=deal_id,
                    source="fast_deal",
                    vehicle_id=vehicle["product_id"],
                    payer=template["payer"],
                    recipient=template["recipient"],
                    calculation_base=base,
                    calculation_base_amount=base_amount,
                    value_type=template["value_type"],
                    value=float(template["value"]),
                    min_amount=template.get("min_amount"),
                    max_amount=template.get("max_amount"),
                    min_percent=template.get("min_percent"),
                    max_percent=template.get("max_percent"),
                    payment_schedule_type=template.get("payment_schedule_type", "days_count"),
                    payment_schedule_period=template.get("payment_schedule_period"),
                    payment_schedule_value=template.get("payment_schedule_value"),
                    comment=template.get("comment", ""),
                    created_by=actor.user_id,
                ),
                session,
            )


def _base_amount(
    base: str,
    *,
    support: Record,
    vehicle: Record,
    deal: Record,
    total: Decimal,
    context: dict[str, Decimal | None] | None,
) -> Decimal:
    """Calculation base of one template, from the confirmed position and deal terms.

    ``application_price`` is the position's final (agreed) price. ``base_price`` (the list
    price) and ``special_price`` are the catalog unit's values as they were when it was
    added to the deal; ``dealer_cost`` is read from the catalog like the exchange does. A
    unit without such a value falls back to the agreed price.
    """
    if base == "support_amount":
        return money(support["support_amount"])
    if base == "down_payment":
        return _down_payment_share(deal, vehicle, total)
    if base in _SNAPSHOT_BASES:
        recorded = (vehicle.get("catalog_snapshot") or {}).get(_SNAPSHOT_BASES[base])
        if recorded is not None:
            return money(recorded)
        return money(vehicle["base_price"] if base == "base_price" else vehicle["final_price"])
    if base == "dealer_cost" and context is not None:
        value = context.get(base)
        if value is not None:
            return money(value)
    return money(vehicle["final_price"])


def _down_payment_share(deal: Record, vehicle: Record, total: Decimal) -> Decimal:
    """The position's part of the deal's advance, in proportion to its final price."""
    down = deal.get("final_down_payment")
    if down is None:
        down = deal.get("down_payment")
    if not down or total <= 0:
        return ZERO
    return money(down * vehicle["final_price"] / total)
