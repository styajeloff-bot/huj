"""Support programs applicable to a fast deal position, their amounts and compatibility.

The matching rule (catalog product, mark, model, VIN, dates, dealer groups) and the
amount formula are the calculator's own; the amount is converted to ``Decimal`` the
moment it leaves the shared rule, so stored money never goes through a float.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from domain.entities.leasing_calculator import (
    SUPPORT_TYPE_DOWN_PAYMENT,
    SUPPORT_TYPE_VEHICLE_DISCOUNT,
    LeasingCalculator,
)
from domain.fast_deals.money import HUNDRED, ZERO, money
from infrastructure.repositories import calculator_repository, support_repository

Record = dict[str, Any]


@dataclass(frozen=True)
class ProgramOffer:
    """One program that applies to a position, with its amount for this deal."""

    program_id: UUID
    name: str
    support_type: str
    amount: Decimal
    base_amount: Decimal
    is_compatible: bool  # with every program already applied to the position
    applied: bool
    starts_at: date | None
    ends_at: date | None


def reduces_price(support_type: str) -> bool:
    """Only vehicle discounts lower the price; the other programs drive compensations."""
    return support_type in SUPPORT_TYPE_VEHICLE_DISCOUNT


def applied_discount(applied: list[Record]) -> Decimal:
    """Price-reducing support already applied to the position."""
    return money(
        sum(
            (item["support_amount"] for item in applied if reduces_price(item["support_type"])),
            ZERO,
        )
    )


def program_amount(
    *,
    support_type: str,
    params: dict[str, Any] | None,
    base_price: Decimal,
    down_payment_percent: Decimal | None,
    discount: Decimal,
) -> tuple[Decimal, Decimal]:
    """``(amount, calculation base)`` of one program for one position.

    Discounts and interest support are computed on the base price. Down payment
    support is computed on the position's share of the advance, which the deal's
    advance percent defines; without it the share, and the amount, are zero.
    """
    if support_type == SUPPORT_TYPE_DOWN_PAYMENT:
        if down_payment_percent is None:
            return ZERO, ZERO
        effective = max(ZERO, base_price - discount)
        share = (effective * down_payment_percent / HUNDRED).quantize(
            Decimal(1), rounding=ROUND_HALF_UP
        )
        return money(_rule(params, share)), money(share)
    return money(_rule(params, base_price)), money(base_price)


def _rule(params: dict[str, Any] | None, base: Decimal) -> int:
    # The shared rule works in whole rubles; its float input is never stored.
    return LeasingCalculator.compute_support_from_params(params, float(base))


def _as_date(value: Any) -> date | None:
    if value is None or isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _compatible(
    program_id: UUID,
    applied_ids: set[UUID],
    flags: dict[UUID, bool],
    graph: dict[UUID, set[UUID]],
) -> bool:
    """A new program must combine with every applied one, in both directions."""
    if not applied_ids or program_id in applied_ids:
        return True
    if not flags.get(program_id, False):
        return False
    neighbours = graph.get(program_id, set())
    return all(flags.get(other, False) and other in neighbours for other in applied_ids)


async def position_offers(
    session: AsyncSession, deal: Record, vehicle: Record, applied: list[Record]
) -> list[ProgramOffer]:
    """Programs applicable to a catalog position; a manual position has none.

    ``applied`` are the programs already applied to this position. The dealer-facing
    discovery view of the calculator is used: programs hidden from clients stay hidden.
    """
    product_id = vehicle.get("product_id")
    if product_id is None:
        return []
    rows = await calculator_repository.get_vehicles_with_support_info(session, [product_id])
    program_ids = sorted(
        {row["support_program_id"] for row in rows if row.get("support_program_id") is not None}
    )
    if not program_ids:
        return []
    details = await calculator_repository.get_support_program_details_by_ids(
        session, program_ids
    )
    applied_ids = {
        item["support_program_id"] for item in applied if item["support_program_id"] is not None
    }
    every_id = sorted({*program_ids, *applied_ids}, key=str)
    flags = await support_repository.get_program_compatibility_flags(session, every_id)
    graph = await support_repository.get_compatibility_by_program_ids(session, every_id)
    discount = applied_discount(applied)
    base_price: Decimal = vehicle["base_price"]
    offers = []
    for detail in details:
        amount, base = program_amount(
            support_type=detail["support_type"],
            params=detail["support_params"],
            base_price=base_price,
            down_payment_percent=deal.get("down_payment_percent"),
            discount=discount,
        )
        offers.append(
            ProgramOffer(
                program_id=detail["id"],
                name=detail["name"],
                support_type=detail["support_type"],
                amount=amount,
                base_amount=base,
                is_compatible=_compatible(detail["id"], applied_ids, flags, graph),
                applied=detail["id"] in applied_ids,
                starts_at=_as_date(detail.get("starts_at")),
                ends_at=_as_date(detail.get("ends_at")),
            )
        )
    return sorted(offers, key=lambda offer: (offer.name.lower(), str(offer.program_id)))
