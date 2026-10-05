"""Compensations of the supports applied to a fast deal (created once, at confirmation).

Applied programs are snapshots in ``application_applied_supports``; at confirmation
each of them gets the compensations its program prescribes, with the source
``fast_deal``. A support request to a distributor is a price instrument only and
never produces a payout.
"""
from __future__ import annotations

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

Record = dict[str, Any]


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
            if base in {"special_price", "dealer_cost"} and context is None:
                context = await comp_repo.get_calculation_context(
                    session,
                    applied_support_id=support["id"],
                    application_id=None,
                    vehicle_id=vehicle["product_id"],
                )
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
                    calculation_base_amount=_base_amount(
                        base, support=support, vehicle=vehicle, deal=deal, total=total,
                        context=context,
                    ),
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

    ``application_price`` is the position's final (agreed) price. ``special_price`` and
    ``dealer_cost`` are the catalog unit's own values; a manual position or a unit
    without them falls back to the agreed price, like the exchange.
    """
    if base == "support_amount":
        return money(support["support_amount"])
    if base == "base_price":
        return money(vehicle["base_price"])
    if base == "down_payment":
        return _down_payment_share(deal, vehicle, total)
    if base in {"special_price", "dealer_cost"} and context is not None:
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
