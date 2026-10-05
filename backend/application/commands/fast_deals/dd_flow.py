"""DD flow (dealer to leasing companies): invitations, offers, choice, final confirmation.

Every handler runs in the caller's transaction under the deal lock and never commits.
Statuses of the deal change only through ``application.fast_deals.lifecycle``; the
statuses of the leasing company invitations change here, next to the rule that moves
them. A reserve failure at sending aborts the whole command.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.fast_deals import lifecycle, notifications, reservation
from application.fast_deals.access import DealContext, invitation, load_for_mutation
from application.fast_deals.actor import Actor
from application.fast_deals.card import build_card
from application.fast_deals.history import bump_and_log
from domain.fast_deals.actions import Action
from domain.fast_deals.errors import (
    FastDealAccessDeniedError,
    FastDealConflictError,
    FastDealStateError,
    FastDealValidationError,
)
from domain.fast_deals.money import nonnegative_money, percent, wire
from domain.fast_deals.terms import require_complete_terms, validate_offer_amounts
from domain.fast_deals.transitions import remaining_after_refusal, restored_lc_status
from domain.fast_deals.values import (
    DealStatus,
    HistoryEvent,
    LcStatus,
    NotifyEvent,
    Party,
    Role,
)
from infrastructure.repositories import fast_deal_access_repository as access_repo
from infrastructure.repositories import fast_deal_repository as repo

Record = dict[str, Any]
# Invitation status changes of one command: ``(invitation after the change, status before)``.
_Moves = list[tuple[Record, str]]

_MAX_REASON_LENGTH = 2000
_MAX_OPTIONAL_TERMS = 50
_MAX_OPTIONAL_KEY_LENGTH = 64
_MAX_OPTIONAL_VALUE_LENGTH = 500
_OFFER_REQUIRED = (
    "financing_amount", "down_payment", "lease_term_months", "monthly_payment", "total_cost",
)
_OFFER_OPTIONAL_MONEY = (
    "markup", "total_interest", "vat_refund", "profit_tax_savings", "total_savings",
)
# What the history keeps of an offer: the terms a leasing company may see about itself.
_OFFER_LOGGED_FIELDS = (
    "total_amount", "down_payment", "down_payment_percent", "lease_term_months",
    "monthly_payment", "buyout_amount", "total_cost",
)


# ------------------------------------------------------------------------------ commands

@dataclass
class SendToLeasingCompaniesCommand:
    actor: Actor
    deal_id: UUID
    if_match: str | None
    leasing_company_ids: list[UUID]


@dataclass
class SubmitOfferCommand:
    actor: Actor
    lc_application_id: UUID
    if_match: str | None
    body: dict[str, Any]


@dataclass
class SelectOfferCommand:
    actor: Actor
    lc_application_id: UUID
    if_match: str | None


@dataclass
class WithdrawSelectionCommand:
    actor: Actor
    deal_id: UUID
    if_match: str | None


@dataclass
class LcConfirmCommand:
    actor: Actor
    lc_application_id: UUID
    if_match: str | None
    file_ids: list[UUID] = field(default_factory=list)


@dataclass
class LcRejectCommand:
    actor: Actor
    lc_application_id: UUID
    if_match: str | None
    reason: str


# ----------------------------------------------------------------------------- send

async def handle_send_to_leasing_companies(
    cmd: SendToLeasingCompaniesCommand, session: AsyncSession
) -> dict[str, Any]:
    """Draft (or a refused deal) → ``pending_lc_confirmation`` with one invitation per LC."""
    ctx = await load_for_mutation(session, cmd.actor, cmd.deal_id, cmd.if_match)
    ctx.require_initiator()
    if not ctx.is_dd:
        raise FastDealStateError("Отправка лизинговым компаниям доступна только в сделке дилера")
    if ctx.status in {DealStatus.DRAFT, DealStatus.REJECTED} and not ctx.vehicles:
        raise FastDealValidationError("Добавьте в сделку хотя бы одну позицию", field="vehicles")
    ctx.require(Action.SEND_TO_LEASING_COMPANIES)
    require_complete_terms(ctx.deal)
    briefs = await _validated_leasing_companies(session, cmd.leasing_company_ids)

    if ctx.status == DealStatus.REJECTED:
        # The refused cycle is archived and a new one starts; the loaded rows are stale.
        ctx.deal = await lifecycle.reopen_rejected(session, ctx)
        ctx.lc_applications = await repo.list_lc_applications(session, ctx.deal_id)
    busy = {
        item["leasing_company_id"]
        for item in ctx.lc_applications
        if item["status"] != LcStatus.REJECTED
    }
    if busy.intersection(cmd.leasing_company_ids):
        raise FastDealConflictError("Сделка уже отправлена одной из выбранных лизинговых компаний")

    deal = ctx.deal
    await reservation.reserve_deal(session, deal, ctx.vehicles, cmd.actor)
    created = [
        await repo.insert_lc_application(
            session,
            {
                "fast_deal_id": deal["id"],
                "leasing_company_id": company_id,
                "status": LcStatus.PENDING_REVIEW.value,
                "review_cycle": deal["review_cycle"],
            },
        )
        for company_id in cmd.leasing_company_ids
    ]
    fresh, version = await lifecycle.change_status(
        session, deal, cmd.actor, DealStatus.PENDING_LC_CONFIRMATION,
        event_type=HistoryEvent.SENT,
    )
    for application in created:
        await bump_and_log(
            session, deal, cmd.actor, HistoryEvent.INVITED,
            changes={
                "leasing_company": {
                    "before": None,
                    "after": briefs[application["leasing_company_id"]]["name"],
                }
            },
            lc_application_id=application["id"],
            review_cycle=application["review_cycle"],
            version=version,
        )
    await notifications.notify(
        session, NotifyEvent.SENT, fresh, cmd.actor, version=version,
        extra={"leasing_company_ids": list(cmd.leasing_company_ids)},
    )
    return {"deal": await build_card(session, cmd.actor, ctx.deal_id)}


async def _validated_leasing_companies(
    session: AsyncSession, company_ids: list[UUID]
) -> dict[UUID, Record]:
    """Unique, non-empty list of active companies of type ``leasing_company``."""
    if not company_ids:
        raise FastDealValidationError(
            "Выберите хотя бы одну лизинговую компанию", field="leasing_company_ids"
        )
    if len(set(company_ids)) != len(company_ids):
        raise FastDealValidationError(
            "Список лизинговых компаний не должен содержать повторов",
            field="leasing_company_ids",
        )
    briefs: dict[UUID, Record] = await access_repo.company_briefs(session, company_ids)
    for company_id in company_ids:
        brief = briefs.get(company_id)
        if brief is None or brief["company_type"] != Role.LEASING_COMPANY or not brief["is_active"]:
            raise FastDealValidationError(
                "Лизинговая компания не найдена или недоступна", field="leasing_company_ids"
            )
    return briefs


# ----------------------------------------------------------------------------- offer

async def handle_submit_offer(cmd: SubmitOfferCommand, session: AsyncSession) -> dict[str, Any]:
    """The invited leasing company gives its single offer (КП) of the review cycle."""
    deal_id = await repo.deal_id_of_lc_application(session, cmd.lc_application_id)
    ctx = await load_for_mutation(session, cmd.actor, deal_id, cmd.if_match)
    application = invitation(ctx, cmd.lc_application_id)
    _require_leasing(ctx)
    if application["status"] == LcStatus.OFFER_SENT or application["current_offer_id"]:
        raise FastDealStateError(
            "Предложение уже отправлено: в одном цикле допускается одно КП"
        )
    ctx.require(Action.SUBMIT_OFFER)

    columns = _offer_columns(cmd.body)
    pdf_file_id: UUID | None = None
    raw_pdf = cmd.body.get("pdf_file_id")
    if raw_pdf is not None:
        from application.fast_deals import file_access

        pdf = await file_access.validate_offer_pdf(
            session, ctx, _as_uuid(raw_pdf, name="pdf_file_id")
        )
        pdf_file_id = pdf["id"]

    deal = ctx.deal
    offer = await repo.insert_offer(
        session,
        {
            **columns,
            "lc_application_id": application["id"],
            "review_cycle": deal["review_cycle"],
            "pdf_file_id": pdf_file_id,
            "created_by": cmd.actor.user_id,
        },
    )
    updated: Record = await repo.update_lc_application(
        session,
        application["id"],
        {"status": LcStatus.OFFER_SENT.value, "current_offer_id": offer["id"]},
    )
    version = await bump_and_log(
        session, deal, cmd.actor, HistoryEvent.OFFER_SENT,
        changes={
            name: {"before": None, "after": _json(columns[name])}
            for name in _OFFER_LOGGED_FIELDS
            if columns.get(name) is not None
        },
        lc_application_id=application["id"],
        review_cycle=deal["review_cycle"],
    )
    await notifications.notify(
        session, NotifyEvent.OFFER_SENT, deal, cmd.actor, version=version, lc_application=updated,
    )
    return {"deal": await build_card(session, cmd.actor, ctx.deal_id)}


def _offer_columns(body: Mapping[str, Any]) -> Record:
    """Typed, validated money columns of an offer; the form field names are reported."""
    for name in _OFFER_REQUIRED:
        if body.get(name) is None:
            raise FastDealValidationError("Заполните обязательное поле", field=name)
    try:
        amounts = validate_offer_amounts(
            total_amount=body["financing_amount"],
            down_payment=body["down_payment"],
            lease_term_months=body["lease_term_months"],
            monthly_payment=body["monthly_payment"],
            total_cost=body["total_cost"],
            buyout_amount=body.get("buyout_amount"),
        )
    except FastDealValidationError as exc:
        if exc.field == "total_amount":
            raise FastDealValidationError(str(exc), field="financing_amount") from exc
        raise
    columns: Record = dict(amounts)
    for name in ("down_payment_percent", "rate"):
        value = body.get(name)
        columns[name] = None if value is None else percent(value, field=name)
    for name in _OFFER_OPTIONAL_MONEY:
        value = body.get(name)
        columns[name] = None if value is None else nonnegative_money(value, field=name)
    columns["optional_financial_terms"] = _optional_terms(body.get("optional_financial_terms"))
    return columns


def _optional_terms(value: Any) -> dict[str, str | int | None]:
    """Other financial terms of the offer: a flat JSON object of scalars."""
    if value is None:
        return {}
    name = "optional_financial_terms"
    if not isinstance(value, Mapping) or len(value) > _MAX_OPTIONAL_TERMS:
        raise FastDealValidationError("Некорректные дополнительные условия", field=name)
    result: dict[str, str | int | None] = {}
    for key, item in value.items():
        if not isinstance(key, str) or not key.strip() or len(key) > _MAX_OPTIONAL_KEY_LENGTH:
            raise FastDealValidationError("Некорректное название условия", field=name)
        if item is None or (isinstance(item, int) and not isinstance(item, bool)):
            result[key] = item
        elif isinstance(item, str) and len(item) <= _MAX_OPTIONAL_VALUE_LENGTH:
            result[key] = item.strip()
        else:
            raise FastDealValidationError(
                "Значение условия — короткая строка или целое число", field=name
            )
    return result


# ---------------------------------------------------------------- choice and its removal

async def handle_select_offer(cmd: SelectOfferCommand, session: AsyncSession) -> dict[str, Any]:
    """The dealer picks one current offer; the other open invitations are closed."""
    deal_id = await repo.deal_id_of_lc_application(session, cmd.lc_application_id)
    ctx = await load_for_mutation(session, cmd.actor, deal_id, cmd.if_match)
    ctx.require_initiator()
    chosen = invitation(ctx, cmd.lc_application_id)
    ctx.require(Action.SELECT_OFFER)
    if chosen["status"] != LcStatus.OFFER_SENT:
        raise FastDealStateError("Выбрать можно только предложение, отправленное лизинговой компанией")
    offer = await _current_offer(session, ctx, chosen)

    moves: _Moves = []
    selected = await _move(
        session, chosen, LcStatus.SELECTED_BY_DEALER, moves,
        columns={"selected_at": datetime.now(UTC)}, log=False,
    )
    for item in ctx.lc_applications:
        if item["id"] != chosen["id"] and item["status"] != LcStatus.REJECTED:
            await _move(session, item, LcStatus.CLOSED_NOT_SELECTED, moves)
    fresh, version = await lifecycle.change_status(
        session, ctx.deal, cmd.actor, DealStatus.PENDING_LC_FINAL_CONFIRMATION,
        event_type=HistoryEvent.OFFER_SELECTED,
        values={"leasing_company_id": chosen["leasing_company_id"], "final_offer_id": offer["id"]},
        lc_application_id=chosen["id"],
    )
    await _log_moves(session, ctx.deal, cmd.actor, moves, version=version)
    await notifications.notify(
        session, NotifyEvent.OFFER_SELECTED, fresh, cmd.actor, version=version,
        lc_application=selected,
    )
    return {"deal": await build_card(session, cmd.actor, ctx.deal_id)}


async def handle_withdraw_selection(
    cmd: WithdrawSelectionCommand, session: AsyncSession
) -> dict[str, Any]:
    """Undo the choice: valid offers become selectable again, refusals stay refusals."""
    ctx = await load_for_mutation(session, cmd.actor, cmd.deal_id, cmd.if_match)
    ctx.require_initiator()
    ctx.require(Action.WITHDRAW_SELECTION)
    chosen = next(
        (item for item in ctx.lc_applications if item["status"] == LcStatus.SELECTED_BY_DEALER),
        None,
    )
    if chosen is None:
        raise FastDealStateError("Выбранное предложение не найдено")

    moves: _Moves = []
    restored = await _move(
        session, chosen, restored_lc_status(chosen), moves,
        columns={"selected_at": None}, log=False,
    )
    await _restore_closed(session, ctx, moves, keep=chosen["id"])
    fresh, version = await lifecycle.change_status(
        session, ctx.deal, cmd.actor, DealStatus.PENDING_LC_CONFIRMATION,
        event_type=HistoryEvent.SELECTION_WITHDRAWN,
        values={"leasing_company_id": None, "final_offer_id": None},
        lc_application_id=chosen["id"],
    )
    await _log_moves(session, ctx.deal, cmd.actor, moves, version=version)
    await notifications.notify(
        session, NotifyEvent.SELECTION_WITHDRAWN, fresh, cmd.actor, version=version,
        lc_application=restored,
    )
    return {"deal": await build_card(session, cmd.actor, ctx.deal_id)}


# -------------------------------------------------------------- final answer of the LC

async def handle_lc_confirm(cmd: LcConfirmCommand, session: AsyncSession) -> dict[str, Any]:
    """The selected leasing company confirms: the terms of its offer become final."""
    from application.fast_deals import file_access

    deal_id = await repo.deal_id_of_lc_application(session, cmd.lc_application_id)
    ctx = await load_for_mutation(session, cmd.actor, deal_id, cmd.if_match)
    application = invitation(ctx, cmd.lc_application_id)
    _require_leasing(ctx)
    ctx.require(Action.CONFIRM_AS_LEASING)
    # Files are uploaded beforehand under their own ACL; here they are only validated.
    await file_access.validate_confirmation_files(session, ctx, cmd.file_ids)
    offer = await _current_offer(session, ctx, application)
    if ctx.deal["final_offer_id"] != offer["id"]:
        raise FastDealStateError("Выбранное предложение изменилось. Обновите карточку")

    ctx.lc_application = await repo.update_lc_application(
        session, application["id"], {"status": LcStatus.CONFIRMED.value}
    )
    await lifecycle.finalize_confirmation(
        session, ctx, final_terms=_final_terms(offer), lc_application_id=application["id"],
    )
    return {"deal": await build_card(session, cmd.actor, ctx.deal_id)}


async def handle_lc_reject(cmd: LcRejectCommand, session: AsyncSession) -> dict[str, Any]:
    """A leasing company refuses; the deal goes on while another one can still answer."""
    deal_id = await repo.deal_id_of_lc_application(session, cmd.lc_application_id)
    ctx = await load_for_mutation(session, cmd.actor, deal_id, cmd.if_match)
    application = invitation(ctx, cmd.lc_application_id)
    _require_leasing(ctx)
    reason = _clean_reason(cmd.reason)
    ctx.require(Action.REJECT_AS_LEASING)

    deal = ctx.deal
    final_stage = ctx.status == DealStatus.PENDING_LC_FINAL_CONFIRMATION
    moves: _Moves = []
    refused = await _move(
        session, application, LcStatus.REJECTED, moves,
        columns={"rejection_reason": reason, "selected_at": None}, log=False,
    )
    if final_stage:
        await _restore_closed(session, ctx, moves, keep=application["id"])
    answering = [
        refused if item["id"] == application["id"] else _after(item, moves)
        for item in ctx.lc_applications
    ]

    if not remaining_after_refusal(answering):
        await bump_and_log(
            session, deal, cmd.actor, HistoryEvent.LC_REJECTED,
            reason=reason, lc_application_id=application["id"],
            review_cycle=deal["review_cycle"],
        )
        # Nobody can answer any more: the deal itself is refused, reservations released.
        await lifecycle.mark_rejected(
            session, ctx, reason=reason, notify_event=NotifyEvent.REJECTED,
            lc_application_id=application["id"],
            # The refusal of the selected company takes its choice back with it.
            values={"leasing_company_id": None, "final_offer_id": None} if final_stage else None,
        )
        return {"deal": await build_card(session, cmd.actor, ctx.deal_id)}

    fresh = deal
    if final_stage:
        fresh, version = await lifecycle.change_status(
            session, deal, cmd.actor, DealStatus.PENDING_LC_CONFIRMATION,
            event_type=HistoryEvent.LC_REJECTED, reason=reason,
            values={"leasing_company_id": None, "final_offer_id": None},
            lc_application_id=application["id"],
        )
    else:
        version = await bump_and_log(
            session, deal, cmd.actor, HistoryEvent.LC_REJECTED,
            reason=reason, lc_application_id=application["id"],
            review_cycle=deal["review_cycle"],
        )
    await _log_moves(session, deal, cmd.actor, moves, version=version)
    await notifications.notify(
        session, NotifyEvent.LC_REJECTED, fresh, cmd.actor, version=version,
        lc_application=refused, extra={"reason": reason},
    )
    return {"deal": await build_card(session, cmd.actor, ctx.deal_id)}


# ---------------------------------------------------------------------------- helpers

def _require_leasing(ctx: DealContext) -> None:
    if ctx.party != Party.LEASING:
        raise FastDealAccessDeniedError("Действие доступно только приглашённой лизинговой компании")


def _clean_reason(value: str | None) -> str:
    reason = (value or "").strip()
    if not reason:
        raise FastDealValidationError("Укажите причину отказа", field="reason")
    if len(reason) > _MAX_REASON_LENGTH:
        raise FastDealValidationError(
            f"Причина не должна быть длиннее {_MAX_REASON_LENGTH} символов", field="reason"
        )
    return reason


def _as_uuid(value: Any, *, name: str) -> UUID:
    try:
        return value if isinstance(value, UUID) else UUID(str(value))
    except ValueError as exc:
        raise FastDealValidationError("Некорректный идентификатор", field=name) from exc


def _json(value: Any) -> Any:
    return wire(value) if isinstance(value, Decimal) else value


async def _current_offer(session: AsyncSession, ctx: DealContext, application: Record) -> Record:
    """The invitation's offer of the current cycle; a stale one is never actionable."""
    offer_id = application["current_offer_id"]
    if offer_id is None:
        raise FastDealStateError("По этому приглашению нет действующего предложения")
    offer: Record | None = await repo.get_offer(session, offer_id)
    if (
        offer is None
        or offer["lc_application_id"] != application["id"]
        or offer["superseded_at"] is not None
        or offer["review_cycle"] != ctx.deal["review_cycle"]
    ):
        raise FastDealStateError("Предложение устарело")
    return offer


def _final_terms(offer: Record) -> Record:
    """Final terms of the deal are copied from the chosen offer."""
    return {
        "final_total_amount": offer["total_amount"],
        "final_down_payment": offer["down_payment"],
        "final_down_payment_percent": offer["down_payment_percent"],
        "final_lease_term_months": offer["lease_term_months"],
        "final_monthly_payment": offer["monthly_payment"],
        "final_total_cost": offer["total_cost"],
        "final_buyout_amount": offer["buyout_amount"],
    }


async def _move(
    session: AsyncSession,
    application: Record,
    to_status: LcStatus,
    moves: _Moves,
    *,
    columns: Record | None = None,
    log: bool = True,
) -> Record:
    """Change an invitation's status; ``log`` queues a history row for the change."""
    updated: Record = await repo.update_lc_application(
        session, application["id"], {"status": to_status.value, **(columns or {})}
    )
    if log and application["status"] != to_status:
        moves.append((updated, application["status"]))
    return updated


async def _restore_closed(
    session: AsyncSession, ctx: DealContext, moves: _Moves, *, keep: UUID
) -> None:
    """Invitations closed by the choice return to the state their offer deserves."""
    for item in ctx.lc_applications:
        if item["id"] != keep and item["status"] == LcStatus.CLOSED_NOT_SELECTED:
            await _move(session, item, restored_lc_status(item), moves)


def _after(item: Record, moves: _Moves) -> Record:
    """The invitation as it is after this command's status changes."""
    for updated, _ in moves:
        if updated["id"] == item["id"]:
            return updated
    return item


async def _log_moves(
    session: AsyncSession, deal: Record, actor: Actor, moves: _Moves, *, version: int
) -> None:
    """One history row per cascaded invitation change, all at the command's version."""
    for application, before in moves:
        await bump_and_log(
            session, deal, actor, HistoryEvent.STATUS_CHANGED,
            changes={"status": {"before": before, "after": application["status"]}},
            lc_application_id=application["id"],
            review_cycle=application["review_cycle"],
            version=version,
        )
