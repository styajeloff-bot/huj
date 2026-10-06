"""Requested leasing terms: advance, term, monthly payment and buyout.

The advance comes in rubles or in percent (never both); the monthly payment is computed
with the calculator's rate unless the user enters it by hand, in which case it is kept
as entered and the recomputed one is stored beside it.
"""
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
from application.fast_deals.access import load_for_mutation
from application.fast_deals.actor import Actor
from application.fast_deals.history import field_changes
from application.fast_deals.rates import current_annual_rate
from domain.fast_deals import terms
from domain.fast_deals.money import ZERO, money
from domain.fast_deals.values import HistoryEvent
from infrastructure.repositories import fast_deal_repository as repo

# Columns that make up the requested terms (the calculation snapshot follows from them).
_TERM_COLUMNS = (
    "down_payment_mode", "down_payment", "down_payment_percent", "lease_term_months",
    "monthly_payment", "monthly_payment_is_manual", "calculated_monthly_payment",
    "buyout_amount",
)
_LOGGED_FIELDS = (
    "down_payment_mode", "down_payment", "down_payment_percent", "lease_term_months",
    "monthly_payment", "monthly_payment_is_manual", "buyout_amount",
)


@dataclass
class UpdateLeasingTermsCommand:
    actor: Actor
    deal_id: UUID
    if_match: str | None
    down_payment: Decimal | None
    down_payment_percent: Decimal | None
    lease_term_months: int
    monthly_payment: Decimal | None
    buyout_amount: Decimal | None


async def handle_update_leasing_terms(
    cmd: UpdateLeasingTermsCommand, session: AsyncSession
) -> dict[str, Any]:
    """Compute the terms for the current total of the positions and store them."""
    ctx = await load_for_mutation(session, cmd.actor, cmd.deal_id, cmd.if_match)
    ensure_editable(ctx)
    total = money(sum((item["final_price"] for item in ctx.vehicles), ZERO))
    down = terms.resolve_down_payment(
        total, amount=cmd.down_payment, percent_value=cmd.down_payment_percent
    )
    built = terms.build_terms(
        total,
        down=down,
        lease_term_months=cmd.lease_term_months,
        buyout=cmd.buyout_amount,
        annual_rate_percent=await current_annual_rate(session),
        manual_monthly_payment=cmd.monthly_payment,
    )
    columns = built.columns()
    if all(ctx.deal.get(name) == columns[name] for name in _TERM_COLUMNS):
        # A repeated save must not reset a deal under review.
        return await unchanged_card(session, ctx)
    scope = await begin_edit(session, ctx)
    await repo.update_deal(session, ctx.deal_id, columns)
    deal, _ = await recalculate(session, scope)
    return await record_and_render(
        session, scope, HistoryEvent.TERMS_CHANGED,
        changes=field_changes(ctx.deal, deal, _LOGGED_FIELDS),
    )
