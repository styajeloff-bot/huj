"""Support programs the dealer may apply to one position of a fast deal."""
from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.fast_deals import support_rules
from application.fast_deals.access import active_vehicle, load_context
from application.fast_deals.actor import Actor
from application.fast_deals.supports_view import is_dealer_side
from domain.fast_deals.errors import FastDealAccessDeniedError
from infrastructure.repositories import fast_deal_support_repository as support_repo

Record = dict[str, Any]

_MANUAL_POSITION_HINT = "Программы поддержки доступны только для техники из каталога"


async def handle_support_programs(
    actor: Actor, deal_id: UUID, vehicle_id: UUID, session: AsyncSession
) -> dict[str, Any]:
    """Programs that apply to the position, with the server-computed amount.

    Dealer side only: a leasing company, a distributor and the platform get a refusal,
    never an empty list that would hint at supports. Amounts are ``Decimal`` (the
    router turns them into exact strings). A manual position has no programs.
    """
    ctx = await load_context(session, actor, deal_id, lock=False)
    if not is_dealer_side(ctx):
        raise FastDealAccessDeniedError("Программы поддержки доступны только дилеру сделки")
    vehicle = active_vehicle(ctx, vehicle_id)
    if vehicle["product_id"] is None:
        return {"items": [], "support_hint": _MANUAL_POSITION_HINT}
    rows: list[Record] = await support_repo.list_applied_supports(session, deal_id)
    applied = [row for row in rows if row["fast_deal_vehicle_id"] == vehicle["id"]]
    offers = await support_rules.position_offers(session, ctx.deal, vehicle, applied)
    return {
        "items": [
            {
                "id": offer.program_id,
                "name": offer.name,
                "support_type": offer.support_type,
                "support_amount": offer.amount,
                "is_compatible": offer.is_compatible,
                "applied": offer.applied,
                "affects_price": support_rules.reduces_price(offer.support_type),
                "starts_at": offer.starts_at,
                "ends_at": offer.ends_at,
            }
            for offer in offers
        ],
        "support_hint": None,
    }
