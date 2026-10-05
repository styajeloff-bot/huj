"""DL flow: a leasing company sends a deal to dealers, the dealer decides or changes it.

The first send splits the draft atomically into one deal per dealer (the original id and
number stay with the first dealer, the others get new ones, every part shares
``group_id`` = the original id). A later send after a refusal goes to the same dealer
without a new split. The dealer confirms unchanged, or sends changes that the leasing
company accepts (confirmed) or rejects with a reason.

Every handler runs under the deal lock inside the router's transaction: any error leaves
nothing behind because the router never commits on an exception.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.fast_deals import (
    lifecycle,
    notifications,
    pending_changes,
    reservation,
)
from application.fast_deals.access import DealContext, load_for_mutation
from application.fast_deals.actor import Actor
from application.fast_deals.card import build_card
from application.fast_deals.history import bump_and_log
from application.fast_deals.numbering import allocate_display_number
from application.fast_deals.rates import current_annual_rate
from domain.fast_deals import split, terms
from domain.fast_deals.actions import Action
from domain.fast_deals.errors import FastDealStateError, FastDealValidationError
from domain.fast_deals.money import ZERO, money
from domain.fast_deals.values import (
    AssigneeRole,
    DealStatus,
    HistoryEvent,
    NotifyEvent,
    Party,
    Role,
    SourceType,
)
from infrastructure.repositories import fast_deal_access_repository as access_repo
from infrastructure.repositories import fast_deal_repository as repo

Record = dict[str, Any]

Group = tuple[UUID, list[Mapping[str, Any]]]


@dataclass
class SendToDealersCommand:
    actor: Actor
    deal_id: UUID
    if_match: str | None


@dataclass
class DealerConfirmCommand:
    actor: Actor
    deal_id: UUID
    if_match: str | None
    file_ids: list[UUID] = field(default_factory=list)


@dataclass
class DealerRejectCommand:
    actor: Actor
    deal_id: UUID
    if_match: str | None
    reason: str


@dataclass
class SendChangesCommand:
    actor: Actor
    deal_id: UUID
    if_match: str | None
    comment: str | None = None


@dataclass
class AcceptChangesCommand:
    actor: Actor
    deal_id: UUID
    if_match: str | None


@dataclass
class RejectChangesCommand:
    actor: Actor
    deal_id: UUID
    if_match: str | None
    reason: str


@dataclass
class _Plan:
    """One dealer's part of a deal that is being split."""

    dealer_id: UUID
    vehicles: list[Mapping[str, Any]]
    total: Decimal
    part_terms: terms.LeasingTerms


# --------------------------------------------------------------------------- send

async def handle_send_to_dealers(
    cmd: SendToDealersCommand, session: AsyncSession
) -> dict[str, Any]:
    """Send the draft to its dealers; the first send splits it, a resend does not."""
    ctx = await load_for_mutation(session, cmd.actor, cmd.deal_id, cmd.if_match)
    ctx.require(Action.SEND_TO_DEALERS)
    terms.require_complete_terms(ctx.deal)
    groups = split.split_groups(ctx.vehicles)
    await _require_dealers(session, groups)
    if ctx.deal["group_id"] is not None:
        _require_same_dealer(ctx.deal, groups)

    # Every check above ran against the loaded state; only now the deal is changed.
    deal = ctx.deal
    if ctx.status == DealStatus.REJECTED:
        deal = await lifecycle.reopen_rejected(session, ctx)
    if deal["group_id"] is None:
        parts = await _split_and_send(session, ctx, deal, groups)
    else:
        parts = [await _send_part(session, cmd.actor, deal)]

    cards = [await build_card(session, cmd.actor, part["id"]) for part in parts]
    return {"group_id": parts[0]["group_id"], "deals": cards}


async def _require_dealers(session: AsyncSession, groups: Sequence[Group]) -> None:
    """Every dealer of a position must still be an active dealer company."""
    briefs: dict[UUID, Record] = await access_repo.company_briefs(
        session, [dealer_id for dealer_id, _ in groups]
    )
    for dealer_id, items in groups:
        brief = briefs.get(dealer_id)
        if brief is None or not brief["is_active"] or brief["company_type"] != Role.DEALER:
            vins = ", ".join(str(item["vin"]) for item in items)
            raise FastDealValidationError(
                f"Дилер позиций (VIN: {vins}) не найден среди действующих дилеров",
                field="dealer_company_id",
            )


def _require_same_dealer(deal: Record, groups: Sequence[Group]) -> None:
    """After the first send the deal belongs to its dealer: no other dealer may join."""
    if len(groups) != 1 or groups[0][0] != deal["dealer_company_id"]:
        raise FastDealValidationError(
            "После первой отправки сделка закреплена за своим дилером: "
            "все позиции должны принадлежать ему",
            field="dealer_company_id",
        )


async def _split_and_send(
    session: AsyncSession, ctx: DealContext, deal: Record, groups: Sequence[Group]
) -> list[Record]:
    """First send: the original deal keeps the first dealer, the others get new deals.

    A single dealer is not a split: the deal only joins its group and the terms stay
    exactly as the leasing company entered them.
    """
    group_id = deal["id"]
    if len(groups) == 1:
        single: Record = await repo.update_deal(
            session, group_id, {"group_id": group_id, "dealer_company_id": groups[0][0]}
        )
        return [await _send_part(session, ctx.actor, single)]

    plans = await _plan_parts(session, deal, groups)
    first, *others = plans
    # The terms of every part come from the same original deal, computed before any write.
    original: Record = await repo.update_deal(
        session,
        group_id,
        {
            "group_id": group_id,
            "dealer_company_id": first.dealer_id,
            "vehicles_total": first.total,
            **first.part_terms.columns(),
        },
    )
    parts = [original]
    client_inn = await _client_inn(session, deal)
    inactive: list[Record] = [
        item
        for item in await repo.list_vehicles(session, group_id, include_inactive=True)
        if item["item_status"] != "active"
    ]
    for plan in others:
        parts.append(await _create_part(session, ctx, deal, plan, client_inn))
        # Removed and replaced positions follow their dealer, not the first one.
        for item in inactive:
            if item["dealer_company_id"] == plan.dealer_id:
                await repo.update_vehicle(
                    session, item["id"], {"fast_deal_id": parts[-1]["id"]}
                )

    sent = [await _send_part(session, ctx.actor, part) for part in parts]
    # Dealers see the history of their own deal: it names the group only, no other part.
    await bump_and_log(
        session,
        sent[0],
        ctx.actor,
        HistoryEvent.SPLIT,
        reason="Сделка разделена по дилерам",
        changes={"group_id": {"before": None, "after": str(group_id)}},
        version=sent[0]["version"],
    )
    return sent


async def _plan_parts(
    session: AsyncSession, deal: Record, groups: Sequence[Group]
) -> list[_Plan]:
    """Totals and terms of every part, all derived from the original deal."""
    rate = await current_annual_rate(session)
    original_total = _total_of(item for _, items in groups for item in items)
    plans: list[_Plan] = []
    for dealer_id, items in groups:
        total = _total_of(items)
        part_terms = terms.split_terms(deal, total, original_total, rate)
        if part_terms is None:
            raise FastDealValidationError(
                "Укажите условия лизинга перед отправкой", field="lease_term_months"
            )
        plans.append(_Plan(dealer_id, list(items), total, part_terms))
    return plans


def _total_of(items: Iterable[Mapping[str, Any]]) -> Decimal:
    return money(sum((item["final_price"] for item in items), ZERO))


async def _client_inn(session: AsyncSession, deal: Record) -> str:
    briefs: dict[UUID, Record] = await access_repo.company_briefs(
        session, [deal["client_company_id"]]
    )
    client = briefs.get(deal["client_company_id"])
    return str(client["inn"]) if client and client["inn"] else ""


async def _create_part(
    session: AsyncSession, ctx: DealContext, deal: Record, plan: _Plan, client_inn: str
) -> Record:
    """A new draft deal of one dealer; its positions move over from the original."""
    number = await allocate_display_number(session, SourceType.LEASING_TO_DEALER, client_inn)
    part: Record = await repo.insert_deal(
        session,
        {
            "display_number": number,
            "source_type": SourceType.LEASING_TO_DEALER.value,
            "status": DealStatus.DRAFT.value,
            "group_id": deal["id"],
            "client_company_id": deal["client_company_id"],
            "client_phone": deal["client_phone"],
            "initiator_company_id": deal["initiator_company_id"],
            "created_by": deal["created_by"],
            "dealer_company_id": plan.dealer_id,
            "leasing_company_id": deal["initiator_company_id"],
            "vehicles_total": plan.total,
            "version": 1,
            "review_cycle": deal["review_cycle"],
            **plan.part_terms.columns(),
        },
    )
    for vehicle in plan.vehicles:
        await repo.update_vehicle(session, vehicle["id"], {"fast_deal_id": part["id"]})
    await _copy_initiator_assignees(session, ctx, part["id"])
    await bump_and_log(
        session,
        part,
        ctx.actor,
        HistoryEvent.SPLIT,
        to_status=DealStatus.DRAFT.value,
        reason="Сделка выделена из общей сделки при разделении по дилерам",
        version=part["version"],
    )
    return part


async def _copy_initiator_assignees(
    session: AsyncSession, ctx: DealContext, deal_id: UUID
) -> None:
    """The responsible employees of the leasing company follow every part."""
    company_id = ctx.deal["initiator_company_id"]
    own = [item for item in ctx.assignees if item["company_id"] == company_id]
    primary = next(
        (item["user_id"] for item in own if item["role"] == AssigneeRole.PRIMARY), None
    )
    if primary is None:
        return
    additional = next(
        (item["user_id"] for item in own if item["role"] == AssigneeRole.ADDITIONAL), None
    )
    await access_repo.replace_company_assignees(
        session,
        deal_id=deal_id,
        company_id=company_id,
        primary_user_id=primary,
        additional_user_id=additional,
        assigned_by=ctx.actor.user_id,
    )


async def _send_part(session: AsyncSession, actor: Actor, deal: Record) -> Record:
    """Reserve, snapshot the sent state and hand one part to its dealer."""
    vehicles: list[Record] = await repo.list_vehicles(session, deal["id"])
    await reservation.reserve_deal(session, deal, vehicles, actor)
    snapshot = await pending_changes.capture_sent_snapshot(session, deal["id"])
    fresh, version = await lifecycle.change_status(
        session,
        deal,
        actor,
        DealStatus.PENDING_DEALER_CONFIRMATION,
        event_type=HistoryEvent.SENT,
        values={"sent_snapshot": snapshot, "has_pending_changes": False},
    )
    await notifications.notify(session, NotifyEvent.SENT, fresh, actor, version=version)
    return fresh


# ------------------------------------------------------------------ dealer decisions

async def handle_dealer_confirm(
    cmd: DealerConfirmCommand, session: AsyncSession
) -> dict[str, Any]:
    """The dealer confirms the deal exactly as it was sent."""
    ctx = await load_for_mutation(session, cmd.actor, cmd.deal_id, cmd.if_match)
    if (
        ctx.party == Party.DEALER
        and ctx.status == DealStatus.PENDING_DEALER_CONFIRMATION
        and ctx.deal["has_pending_changes"]
    ):
        raise FastDealStateError("В сделке есть изменения: отправьте их лизинговой компании")
    ctx.require(Action.CONFIRM_AS_DEALER)

    from application.fast_deals import file_access

    await file_access.validate_confirmation_files(session, ctx, cmd.file_ids)
    await lifecycle.finalize_confirmation(
        session, ctx, final_terms=_final_terms(ctx.deal)
    )
    return {"deal": await build_card(session, cmd.actor, ctx.deal_id)}


async def handle_dealer_reject(
    cmd: DealerRejectCommand, session: AsyncSession
) -> dict[str, Any]:
    """The dealer refuses the deal; the reason is mandatory."""
    ctx = await load_for_mutation(session, cmd.actor, cmd.deal_id, cmd.if_match)
    ctx.require(Action.REJECT_AS_DEALER)
    reason = _require_reason(cmd.reason)
    await lifecycle.mark_rejected(
        session, ctx, reason=reason, notify_event=NotifyEvent.REJECTED
    )
    return {"deal": await build_card(session, cmd.actor, ctx.deal_id)}


# ------------------------------------------------------------------- change cycle

async def handle_send_changes(
    cmd: SendChangesCommand, session: AsyncSession
) -> dict[str, Any]:
    """The dealer sends its changes to the leasing company for a decision."""
    ctx = await load_for_mutation(session, cmd.actor, cmd.deal_id, cmd.if_match)
    ctx.require(Action.SEND_CHANGES)
    # The difference is recomputed here: what is sent is what is stored in history.
    deal, diff = await pending_changes.refresh_pending_changes(session, ctx.deal_id)
    if not diff:
        raise FastDealStateError("Нет изменений для отправки")
    comment = _clean_text(cmd.comment)
    fresh, version = await lifecycle.change_status(
        session,
        deal,
        cmd.actor,
        DealStatus.PENDING_LC_CHANGES_CONFIRMATION,
        event_type=HistoryEvent.CHANGES_SENT,
        reason=comment,
        changes={"positions": diff},
    )
    await notifications.notify(
        session,
        NotifyEvent.CHANGES_SENT,
        fresh,
        cmd.actor,
        version=version,
        extra={"changes": diff, "comment": comment},
    )
    return {"deal": await build_card(session, cmd.actor, ctx.deal_id)}


async def handle_accept_changes(
    cmd: AcceptChangesCommand, session: AsyncSession
) -> dict[str, Any]:
    """The leasing company accepts the dealer's changes: the deal is confirmed."""
    ctx = await load_for_mutation(session, cmd.actor, cmd.deal_id, cmd.if_match)
    ctx.require(Action.ACCEPT_CHANGES)
    await lifecycle.finalize_confirmation(
        session,
        ctx,
        final_terms=_final_terms(ctx.deal),
        event_type=HistoryEvent.CHANGES_ACCEPTED,
    )
    return {"deal": await build_card(session, cmd.actor, ctx.deal_id)}


async def handle_reject_changes(
    cmd: RejectChangesCommand, session: AsyncSession
) -> dict[str, Any]:
    """The leasing company refuses the changes; it may correct the deal and send again."""
    ctx = await load_for_mutation(session, cmd.actor, cmd.deal_id, cmd.if_match)
    ctx.require(Action.REJECT_CHANGES)
    reason = _require_reason(cmd.reason)
    await lifecycle.mark_rejected(
        session,
        ctx,
        reason=reason,
        notify_event=NotifyEvent.CHANGES_REJECTED,
        event_type=HistoryEvent.CHANGES_REJECTED,
    )
    return {"deal": await build_card(session, cmd.actor, ctx.deal_id)}


# ----------------------------------------------------------------------- helpers

def _final_terms(deal: Record) -> Record:
    """Final terms of a DL deal: the terms currently requested, nothing is negotiated."""
    terms.require_complete_terms(deal)
    down_payment: Decimal = deal["down_payment"]
    monthly_payment: Decimal = deal["monthly_payment"]
    term: int = deal["lease_term_months"]
    buyout: Decimal = deal.get("buyout_amount") or ZERO
    return {
        "final_total_amount": money(deal["vehicles_total"] - down_payment),
        "final_down_payment": down_payment,
        "final_down_payment_percent": deal["down_payment_percent"],
        "final_lease_term_months": term,
        "final_monthly_payment": monthly_payment,
        "final_total_cost": terms.contract_cost(down_payment, monthly_payment, term, buyout),
        "final_buyout_amount": buyout,
    }


def _clean_text(value: str | None) -> str | None:
    text = (value or "").strip()
    return text or None


def _require_reason(value: str | None) -> str:
    reason = _clean_text(value)
    if reason is None:
        raise FastDealValidationError("Укажите причину", field="reason")
    return reason
