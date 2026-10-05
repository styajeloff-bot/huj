"""Shared lifecycle of a deal: status changes, reset, reopening, cancel, confirmation.

Both flows (DD and DL) go through these functions so that reservations, review
cycles, history and notifications behave identically. Every function runs inside the
caller's transaction under the deal lock and never commits.
"""
from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from application.fast_deals import (
    monetization,
    notifications,
    reservation,
    supports,
)
from application.fast_deals.access import DealContext
from application.fast_deals.actor import Actor
from application.fast_deals.history import bump_and_log
from domain.fast_deals.errors import FastDealStateError
from domain.fast_deals.money import ZERO, money
from domain.fast_deals.transitions import require_transition
from domain.fast_deals.values import (
    DD_IN_REVIEW,
    DealStatus,
    HistoryEvent,
    NotifyEvent,
    Party,
    SourceType,
)
from infrastructure.repositories import fast_deal_repository as repo

Record = dict[str, Any]

_TIMESTAMP_OF = {
    DealStatus.REJECTED: "rejected_at",
    DealStatus.CANCELLED: "cancelled_at",
    DealStatus.CONFIRMED: "confirmed_at",
}
_SENT_STATUSES = {
    DealStatus.PENDING_LC_CONFIRMATION,
    DealStatus.PENDING_DEALER_CONFIRMATION,
}
# Columns cleared whenever a deal returns to a draft or starts a new review cycle.
_CLEARED_FINAL_TERMS: Record = {
    "final_offer_id": None,
    "final_total_amount": None,
    "final_down_payment": None,
    "final_down_payment_percent": None,
    "final_lease_term_months": None,
    "final_monthly_payment": None,
    "final_total_cost": None,
    "final_buyout_amount": None,
    "has_pending_changes": False,
    "sent_snapshot": None,
}


async def change_status(
    session: AsyncSession,
    deal: Record,
    actor: Actor,
    to_status: DealStatus,
    *,
    event_type: str,
    reason: str | None = None,
    values: Record | None = None,
    changes: Record | None = None,
    lc_application_id: Any = None,
) -> tuple[Record, int]:
    """Validated transition + timestamps + one history row; returns the fresh deal.

    ``sent_at`` records the first sending only: a draft that was ever sent can never
    be deleted, only cancelled.
    """
    require_transition(deal["source_type"], deal["status"], to_status)
    columns: Record = {"status": to_status.value}
    timestamp = _TIMESTAMP_OF.get(to_status)
    if timestamp is not None:
        columns[timestamp] = datetime.now(UTC)
    if to_status in {DealStatus.REJECTED, DealStatus.CANCELLED}:
        columns["status_reason"] = reason
    elif to_status == DealStatus.DRAFT:
        columns["status_reason"] = None
    if to_status in _SENT_STATUSES and deal["sent_at"] is None:
        columns["sent_at"] = datetime.now(UTC)
    columns.update(values or {})
    await repo.update_deal(session, deal["id"], columns)
    version = await bump_and_log(
        session,
        deal,
        actor,
        event_type,
        from_status=deal["status"],
        to_status=to_status.value,
        reason=reason,
        changes=changes,
        lc_application_id=lc_application_id,
        review_cycle=columns.get("review_cycle", deal["review_cycle"]),
    )
    fresh: Record | None = await repo.get_deal(session, deal["id"])
    assert fresh is not None
    return fresh, version


async def reset_to_draft(session: AsyncSession, ctx: DealContext, *, reason: str) -> Record:
    """DD: a business change after sending closes the cycle and returns a draft.

    Reservations are released, previous offers are superseded and invitations
    archived (history stays), the choice and final terms are cleared, and the
    participants of the previous cycle are told.
    """
    deal = ctx.deal
    await reservation.release_deal(session, deal["id"], reason=reason)
    archived = await repo.archive_current_cycle(session, deal["id"])
    values: Record = {
        **_CLEARED_FINAL_TERMS,
        "review_cycle": deal["review_cycle"] + 1,
        "leasing_company_id": None,
    }
    fresh, version = await change_status(
        session, deal, ctx.actor, DealStatus.DRAFT,
        event_type=HistoryEvent.RESET, reason=reason, values=values,
    )
    await notifications.notify(
        session, NotifyEvent.RESET, fresh, ctx.actor, version=version,
        extra={
            "reason": reason,
            "previous_lc_company_ids": [
                item["leasing_company_id"] for item in archived if item["status"] != "rejected"
            ],
        },
    )
    return fresh


async def reopen_rejected(session: AsyncSession, ctx: DealContext) -> Record:
    """The initiator corrects a refused deal: it returns to a draft.

    DD starts a new review cycle (the refused invitations are archived and may be
    invited again as new records); DL keeps its dealer, so a resend goes to the same
    dealer without a new split. Reservations were already released at refusal.
    """
    deal = ctx.deal
    values: Record = {**_CLEARED_FINAL_TERMS}
    if deal["source_type"] == SourceType.DEALER_TO_LEASING:
        await repo.archive_current_cycle(session, deal["id"])
        values["review_cycle"] = deal["review_cycle"] + 1
        values["leasing_company_id"] = None
    fresh, _ = await change_status(
        session, deal, ctx.actor, DealStatus.DRAFT,
        event_type=HistoryEvent.REOPENED, values=values,
    )
    return fresh


async def prepare_initiator_mutation(session: AsyncSession, ctx: DealContext) -> Record:
    """Entry of every initiator business change; returns the deal now editable.

    A draft is edited as it is. A refused deal is reopened to a draft. A DD deal that
    is under review is reset to a draft (new cycle). Confirmed, cancelled and DL deals
    that wait for the dealer are closed to the initiator's changes.
    """
    if ctx.party != Party.INITIATOR:
        raise FastDealStateError("Изменять сделку может только её инициатор")
    status = ctx.status
    if status == DealStatus.DRAFT:
        return ctx.deal
    if status == DealStatus.REJECTED:
        return await reopen_rejected(session, ctx)
    if ctx.is_dd and status in DD_IN_REVIEW:
        return await reset_to_draft(
            session, ctx, reason="Дилер изменил данные сделки после отправки"
        )
    raise FastDealStateError("Сделку нельзя изменить в текущем статусе")


async def cancel_deal(session: AsyncSession, ctx: DealContext, *, reason: str | None) -> Record:
    """The initiator cancels an unfinished deal; reservations are released, no way back."""
    deal = ctx.deal
    await reservation.release_deal(session, deal["id"], reason="Сделка отменена")
    fresh, version = await change_status(
        session, deal, ctx.actor, DealStatus.CANCELLED,
        event_type=HistoryEvent.CANCELLED, reason=reason,
    )
    await notifications.notify(
        session, NotifyEvent.CANCELLED, fresh, ctx.actor, version=version,
        extra={"reason": reason},
    )
    return fresh


async def mark_rejected(
    session: AsyncSession,
    ctx: DealContext,
    *,
    reason: str,
    notify_event: str,
    event_type: str = HistoryEvent.REJECTED,
    lc_application_id: Any = None,
) -> Record:
    """Refusal with a reason: reservations are released, the deal becomes ``rejected``."""
    deal = ctx.deal
    await reservation.release_deal(session, deal["id"], reason="Сделка отклонена")
    fresh, version = await change_status(
        session, deal, ctx.actor, DealStatus.REJECTED,
        event_type=event_type, reason=reason, lc_application_id=lc_application_id,
    )
    await notifications.notify(
        session, notify_event, fresh, ctx.actor, version=version,
        lc_application=None, extra={"reason": reason},
    )
    return fresh


def confirmed_amount_of(vehicles: list[Record]) -> Decimal:
    """Immutable base of the deal: the sum of ``final_price`` of active positions."""
    return money(sum((item["final_price"] for item in vehicles), ZERO))


async def finalize_confirmation(
    session: AsyncSession,
    ctx: DealContext,
    *,
    final_terms: Record,
    event_type: str = HistoryEvent.CONFIRMED,
    lc_application_id: Any = None,
    values: Record | None = None,
) -> Record:
    """The single transition to ``confirmed`` and everything that follows from it.

    Order: fix ``confirmed_amount`` and final terms → complete reservations (products
    become sold) → compensations of applied programs → monetization capture (its
    failure never undoes the confirmation) → notifications. Re-running it on a
    confirmed deal is refused by the transition guard, so nothing is duplicated.
    """
    deal = ctx.deal
    vehicles: list[Record] = await repo.list_vehicles(session, deal["id"])
    amount = confirmed_amount_of(vehicles)
    columns: Record = {
        "confirmed_amount": amount,
        "has_pending_changes": False,
        **final_terms,
        **(values or {}),
    }
    fresh, version = await change_status(
        session, deal, ctx.actor, DealStatus.CONFIRMED,
        event_type=event_type, values=columns, lc_application_id=lc_application_id,
    )
    await reservation.complete_deal(session, deal["id"])
    await supports.create_compensations_on_confirm(session, fresh, ctx.actor)
    await monetization.capture_confirmed_deal(session, fresh, ctx.actor)
    await notifications.notify(
        session, NotifyEvent.CONFIRMED, fresh, ctx.actor, version=version,
        lc_application=ctx.lc_application,
    )
    return fresh
