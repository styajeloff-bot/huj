"""Shared steps of every command that edits the business data of a deal.

Who may edit: the initiator, whose change after sending reopens a refused deal or
resets a DD under review (``lifecycle.prepare_initiator_mutation``), and the dealer of
a DL deal, who may only correct price and manual position data and thereby creates
pending changes. A command validates its input first, returns the unchanged card when
there is nothing to change (so a repeated save never resets a deal), and otherwise runs
``begin_edit`` → mutate → ``recalculate`` → ``record_and_render``.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from application.fast_deals import lifecycle, pending_changes, pricing
from application.fast_deals.access import DealContext
from application.fast_deals.card import build_card
from application.fast_deals.history import bump_and_log
from domain.fast_deals.actions import Action
from domain.fast_deals.errors import FastDealAccessDeniedError
from domain.fast_deals.values import Party

Record = dict[str, Any]


@dataclass
class EditScope:
    """A deal that is open for a change by the current command."""

    ctx: DealContext
    deal: Record  # editable deal: reopened or reset when the command had to do so
    bumped: bool  # the reopen/reset already advanced the version in this command


def ensure_editable(ctx: DealContext, *, dealer_allowed: bool = False) -> None:
    """403/409 unless the actor may change business data in the current status.

    ``dealer_allowed`` lets the DL dealer through for the few changes it may make;
    positions, options and leasing terms stay with the initiator.
    """
    if ctx.party not in {Party.INITIATOR, Party.DEALER}:
        raise FastDealAccessDeniedError("Изменять сделку может только её инициатор")
    ctx.require(Action.EDIT, "Сделку нельзя изменить в текущем статусе")
    if ctx.party == Party.DEALER and not dealer_allowed:
        raise FastDealAccessDeniedError(
            "Состав техники, опции и условия лизинга меняет лизинговая компания: "
            "дилер может изменить цену и данные ручных позиций"
        )


async def begin_edit(
    session: AsyncSession, ctx: DealContext, *, dealer_allowed: bool = False
) -> EditScope:
    """Open the deal for a change: the initiator's change reopens or resets it first."""
    ensure_editable(ctx, dealer_allowed=dealer_allowed)
    if ctx.party == Party.DEALER:
        return EditScope(ctx=ctx, deal=ctx.deal, bumped=False)
    deal = await lifecycle.prepare_initiator_mutation(session, ctx)
    return EditScope(ctx=ctx, deal=deal, bumped=deal["version"] != ctx.deal["version"])


async def recalculate(session: AsyncSession, scope: EditScope) -> tuple[Record, list[Record]]:
    """Reprice the positions, rebase the terms and (DL dealer) refresh pending changes.

    Returns the fresh deal and its active positions.
    """
    deal_id = scope.deal["id"]
    deal, vehicles = await pricing.refresh_deal_totals(session, deal_id)
    if scope.ctx.party == Party.DEALER:
        deal, _ = await pending_changes.refresh_pending_changes(session, deal_id)
    return deal, vehicles


async def record_and_render(
    session: AsyncSession,
    scope: EditScope,
    event_type: str,
    *,
    changes: Record | None,
) -> Record:
    """One version bump and one history row for the command, then the fresh card.

    A reopen or reset inside the same command has already advanced the version: the
    command's own event then describes that version instead of bumping it again.
    """
    await bump_and_log(
        session,
        scope.deal,
        scope.ctx.actor,
        event_type,
        changes=changes or None,
        version=scope.deal["version"] if scope.bumped else None,
    )
    return {"deal": await build_card(session, scope.ctx.actor, scope.deal["id"])}


async def unchanged_card(session: AsyncSession, ctx: DealContext) -> Record:
    """Nothing to change: the current card, no reset, no version bump, no history."""
    return {"deal": await build_card(session, ctx.actor, ctx.deal_id)}
