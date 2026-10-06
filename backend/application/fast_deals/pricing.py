"""Recalculation of position prices and of the deal totals and terms.

The server alone computes ``final_price`` and ``support_amount``: a client value for
either is never trusted. Support is counted exactly once.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.fast_deals.rates import current_annual_rate
from domain.fast_deals import pricing, terms
from domain.fast_deals.errors import FastDealNotFoundError
from domain.fast_deals.money import ZERO, money
from infrastructure.repositories import fast_deal_repository as repo
from infrastructure.repositories import fast_deal_support_repository as support_repo

Record = dict[str, Any]


def priced_columns(
    vehicle: Record, support_amount: Decimal
) -> tuple[Decimal, Decimal, Decimal]:
    """``(final_price, effective_support, options_amount)`` of a position row."""
    equipments = pricing.options_total(vehicle.get("equipments") or [])
    services = pricing.options_total(vehicle.get("services") or [])
    final, effective = pricing.compute_final_price(
        base_price=vehicle["base_price"],
        adjustment_type=vehicle.get("adjustment_type"),
        adjustment_amount=vehicle.get("adjustment_amount"),
        support_amount=support_amount,
        equipments_total=equipments,
        services_total=services,
    )
    return final, effective, money(equipments + services)


async def reprice_vehicle(
    session: AsyncSession, vehicle_id: UUID, *, accounted: dict[UUID, Decimal] | None = None
) -> Record:
    """Recompute one position from its base, adjustment, options and accounted support."""
    vehicle = await repo.get_vehicle(session, vehicle_id)
    if vehicle is None:
        raise FastDealNotFoundError("Позиция не найдена")
    if accounted is None:
        accounted = await support_repo.accounted_support_by_vehicle(
            session, vehicle["fast_deal_id"]
        )
    final, effective, options_amount = priced_columns(vehicle, accounted.get(vehicle_id, ZERO))
    updated: Record = await repo.update_vehicle(
        session,
        vehicle_id,
        {"final_price": final, "support_amount": effective, "options_amount": options_amount},
    )
    return updated


async def refresh_deal_totals(session: AsyncSession, deal_id: UUID) -> tuple[Record, list[Record]]:
    """Reprice every active position, then rebase the deal terms on the new total.

    Terms keep their input mode; a manual monthly payment survives the change and the
    recomputed one is stored beside it. Incomplete terms are left as they are.
    """
    deal = await repo.get_deal(session, deal_id)
    if deal is None:
        raise FastDealNotFoundError
    accounted = await support_repo.accounted_support_by_vehicle(session, deal_id)
    vehicles = [
        await reprice_vehicle(session, vehicle["id"], accounted=accounted)
        for vehicle in await repo.list_vehicles(session, deal_id)
    ]
    total = money(sum((item["final_price"] for item in vehicles), ZERO))
    values: Record = {"vehicles_total": total}
    rebased = terms.rebase_terms(deal, total, await current_annual_rate(session))
    if rebased is not None:
        values.update(rebased.columns())
    deal = await repo.update_deal(session, deal_id, values)
    return deal, vehicles
