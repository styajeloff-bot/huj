"""Supports of fast deal positions: programs, requests to a distributor, decisions.

Only the dealer's side of a deal works with supports (the initiator of a DD, the dealer
of a DL part); a leasing company never does. Applying or removing a program and
accounting an approved amount change the price, so they are business changes: a DD
goes through the normal reset to a draft, a DL dealer through the change cycle. A
request and a distributor's decision change no price by themselves.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.fast_deals import (
    lifecycle,
    notifications,
    pending_changes,
    pricing,
    support_rules,
)
from application.fast_deals.access import DealContext, active_vehicle, load_for_mutation
from application.fast_deals.actor import Actor
from application.fast_deals.card import build_card
from application.fast_deals.history import bump_and_log, field_changes
from application.fast_deals.supports_view import (
    NO_DISTRIBUTOR_HINT,
    OPEN_REQUEST_STATUSES,
    dealer_may_change_supports,
    is_dealer_side,
    resolve_distributors,
    support_action_facts,
)
from domain.fast_deals.actions import Action
from domain.fast_deals.errors import (
    FastDealAccessDeniedError,
    FastDealConflictError,
    FastDealNotFoundError,
    FastDealStateError,
    FastDealValidationError,
)
from domain.fast_deals.money import ZERO, positive_money, wire
from domain.fast_deals.values import (
    DealStatus,
    HistoryEvent,
    NotifyEvent,
    Party,
    SupportRequestStatus,
)
from domain.monetization.sources import support_origin
from infrastructure.repositories import compensation_repository as comp_repo
from infrastructure.repositories import fast_deal_access_repository as access_repo
from infrastructure.repositories import fast_deal_repository as repo
from infrastructure.repositories import fast_deal_support_repository as support_repo
from infrastructure.repositories import support_repository

Record = dict[str, Any]

_MAX_COMMENT_LENGTH = 2000
_PRICE_FIELDS = ("support_amount", "final_price")
_DECISIONS = frozenset(
    {
        SupportRequestStatus.CANCELLED,
        SupportRequestStatus.PRE_APPROVED,
        SupportRequestStatus.APPROVED,
    }
)


@dataclass
class ApplySupportProgramCommand:
    actor: Actor
    deal_id: UUID
    vehicle_id: UUID
    if_match: str | None
    support_program_id: UUID


@dataclass
class RemoveAppliedSupportCommand:
    actor: Actor
    deal_id: UUID
    vehicle_id: UUID
    applied_id: UUID
    if_match: str | None


@dataclass
class RequestSupportCommand:
    actor: Actor
    deal_id: UUID
    vehicle_id: UUID
    if_match: str | None
    amount: Decimal
    comment: str | None = None


@dataclass
class DecideSupportCommand:
    actor: Actor
    request_id: UUID
    if_match: str | None
    status: str
    decided_amount: Decimal | None = None
    comment: str | None = None


@dataclass
class ApplyApprovedSupportCommand:
    actor: Actor
    deal_id: UUID
    vehicle_id: UUID
    if_match: str | None


# ------------------------------------------------------------------------ programs

async def handle_apply_support_program(
    cmd: ApplySupportProgramCommand, session: AsyncSession
) -> dict[str, Any]:
    """Apply a program of the catalog unit; the server computes the amount.

    The program must apply to the unit and combine with every program already applied.
    The applied row is a snapshot: later changes of the program do not touch it.
    """
    ctx = await load_for_mutation(session, cmd.actor, cmd.deal_id, cmd.if_match)
    _require_dealer_side(ctx)
    ctx.require(Action.EDIT)
    vehicle = active_vehicle(ctx, cmd.vehicle_id)
    if vehicle["product_id"] is None:
        raise FastDealValidationError(
            "Программы поддержки применяются только к технике из каталога",
            field="support_program_id",
        )
    applied = await _applied_of(session, ctx, vehicle)
    offers = await support_rules.position_offers(session, ctx.deal, vehicle, applied)
    offer = next((item for item in offers if item.program_id == cmd.support_program_id), None)
    if offer is None:
        raise FastDealValidationError(
            "Программа поддержки недоступна для этой техники", field="support_program_id"
        )
    if offer.applied:
        raise FastDealConflictError("Программа уже применена к этой позиции")
    if not offer.is_compatible:
        raise FastDealValidationError(
            "Программа несовместима с уже применёнными к этой позиции",
            field="support_program_id",
        )
    if offer.amount <= 0:
        raise FastDealValidationError(_zero_amount_message(offer, ctx.deal), field="support_program_id")
    program = await support_repository.get_program_by_id(session, offer.program_id)
    if program is None:
        raise FastDealValidationError("Программа поддержки не найдена", field="support_program_id")

    deal, advanced = await _begin_dealer_change(session, ctx)
    templates = program.get("compensation_templates") or []
    distributor_id = await access_repo.distributor_of_dealer(session, deal["dealer_company_id"])
    await comp_repo.create_applied_support(
        session,
        {
            "fast_deal_id": ctx.deal_id,
            "fast_deal_vehicle_id": vehicle["id"],
            "vehicle_id": vehicle["product_id"],
            "support_program_id": offer.program_id,
            **support_origin(program, deal["dealer_company_id"], distributor_id),
            "name": program["name"],
            "support_type": program["support_type"],
            "support_params": program.get("support_params") or {},
            "comment": program.get("comment"),
            "starts_at": program.get("starts_at"),
            "ends_at": program.get("ends_at"),
            "main_payer": templates[0]["payer"] if templates else None,
            "base_amount": offer.base_amount,
            "support_amount": offer.amount,
        },
    )
    deal, repriced = await _reprice(session, ctx)
    changes = {
        _key(vehicle, "support_program"): {"before": None, "after": offer.name},
        **_price_changes(vehicle, repriced),
    }
    await bump_and_log(
        session, deal, cmd.actor, HistoryEvent.SUPPORT_APPLIED, changes=changes, version=advanced
    )
    return {"deal": await build_card(session, cmd.actor, ctx.deal_id)}


async def handle_remove_applied_support(
    cmd: RemoveAppliedSupportCommand, session: AsyncSession
) -> dict[str, Any]:
    """Take an applied program off a position; its price effect is recomputed."""
    ctx = await load_for_mutation(session, cmd.actor, cmd.deal_id, cmd.if_match)
    _require_dealer_side(ctx)
    ctx.require(Action.EDIT)
    vehicle = active_vehicle(ctx, cmd.vehicle_id)
    row = await support_repo.get_applied_support(session, cmd.applied_id)
    if (
        row is None
        or row["fast_deal_id"] != ctx.deal_id
        or row["fast_deal_vehicle_id"] != vehicle["id"]
    ):
        raise FastDealNotFoundError("Применённая поддержка не найдена")
    if await comp_repo.count_compensations_for_support(session, row["id"]):
        raise FastDealStateError("По применённой поддержке уже созданы компенсации")

    deal, advanced = await _begin_dealer_change(session, ctx)
    await support_repo.delete_applied_support(session, row["id"])
    deal, repriced = await _reprice(session, ctx)
    changes = {
        _key(vehicle, "support_program"): {"before": row["name"], "after": None},
        **_price_changes(vehicle, repriced),
    }
    await bump_and_log(
        session, deal, cmd.actor, HistoryEvent.SUPPORT_REMOVED, changes=changes, version=advanced
    )
    return {"deal": await build_card(session, cmd.actor, ctx.deal_id)}


# ------------------------------------------------------------------------- requests

async def handle_request_support(
    cmd: RequestSupportCommand, session: AsyncSession
) -> dict[str, Any]:
    """Ask the dealer's own distributor for additional support on one position.

    The distributor is never chosen by the caller: it is the dealer's linked
    distributor that actively serves the position's mark. A request changes no price
    and does not reset the deal.
    """
    ctx = await load_for_mutation(session, cmd.actor, cmd.deal_id, cmd.if_match)
    _require_dealer_side(ctx)
    if not dealer_may_change_supports(ctx):
        raise FastDealStateError("Запрос поддержки недоступен в текущем состоянии сделки")
    vehicle = active_vehicle(ctx, cmd.vehicle_id)
    amount = positive_money(cmd.amount, field="amount")
    comment = _comment(cmd.comment, field="comment")
    distributor_id = (await resolve_distributors(session, ctx.deal, [vehicle])).get(vehicle["id"])
    if distributor_id is None:
        raise FastDealStateError(NO_DISTRIBUTOR_HINT)
    requests = await support_repo.list_support_requests(session, ctx.deal_id)
    if any(
        item["fast_deal_vehicle_id"] == vehicle["id"] and item["status"] in OPEN_REQUEST_STATUSES
        for item in requests
    ):
        raise FastDealConflictError("По позиции уже есть открытый запрос поддержки")
    ctx.require(Action.REQUEST_SUPPORT, **await support_action_facts(session, ctx))

    request = await support_repo.insert_support_request(
        session,
        {
            "fast_deal_vehicle_id": vehicle["id"],
            "fast_deal_id": ctx.deal_id,
            "distributor_company_id": distributor_id,
            "requested_amount": amount,
            "status": SupportRequestStatus.REQUESTED.value,
            "requested_by": cmd.actor.user_id,
            "comment": comment,
        },
    )
    changes = {
        _key(vehicle, "support_request"): {"before": None, "after": request["status"]},
        _key(vehicle, "support_requested_amount"): {"before": None, "after": wire(amount)},
    }
    version = await bump_and_log(
        session, ctx.deal, cmd.actor, HistoryEvent.SUPPORT_REQUESTED, changes=changes, reason=comment
    )
    await notifications.notify(
        session, NotifyEvent.SUPPORT_REQUESTED, ctx.deal, cmd.actor, version=version,
        extra={"support_request": _notification_payload(request, vehicle)},
    )
    return {"deal": await build_card(session, cmd.actor, ctx.deal_id)}


async def handle_decide_support(
    cmd: DecideSupportCommand, session: AsyncSession
) -> dict[str, Any]:
    """The distributor decides a request addressed to its own company.

    Reject (``cancelled``), pre-approve (price unchanged) or approve with a decided
    amount that may differ from the requested one. Approval does not lower the price
    by itself: the dealer applies it (the amount is shown as unaccounted), except in a
    DD draft, where the approved amount is accounted at once.
    """
    deal_id = await repo.deal_id_of_support_request(session, cmd.request_id)
    ctx = await load_for_mutation(session, cmd.actor, deal_id, cmd.if_match)
    if ctx.party != Party.DISTRIBUTOR:
        raise FastDealAccessDeniedError("Решение по запросу поддержки принимает дистрибьютор")
    request: Record | None = await support_repo.get_support_request(
        session, cmd.request_id, lock=True
    )
    if (
        request is None
        or request["fast_deal_id"] != ctx.deal_id
        or request["distributor_company_id"] != cmd.actor.company_id
    ):
        raise FastDealNotFoundError("Запрос поддержки не найден")
    vehicle = next((item for item in ctx.vehicles if item["id"] == request["fast_deal_vehicle_id"]), None)
    if vehicle is None:
        raise FastDealStateError("Позиция запроса удалена из сделки")
    ctx.require(
        Action.DECIDE_SUPPORT,
        "Решения закрыты: сделка завершена или запрос уже решён",
        **await support_action_facts(session, ctx),
    )
    status, decided = _validated_decision(cmd, request)
    comment = _comment(cmd.comment, field="comment")
    account_now = status == SupportRequestStatus.APPROVED and ctx.is_dd and ctx.status == DealStatus.DRAFT
    values: Record = {
        "status": status.value,
        "decided_amount": decided,
        "decision_comment": comment,
        "decided_by": cmd.actor.user_id,
        "decided_at": datetime.now(UTC),
    }
    if account_now:
        values["accounted_amount"] = decided
    updated = await support_repo.update_support_request(session, request["id"], values)

    deal = ctx.deal
    changes: Record = {
        _key(vehicle, "support_request"): {"before": request["status"], "after": updated["status"]},
        _key(vehicle, "support_decided_amount"): {
            "before": wire(request["decided_amount"]), "after": wire(decided),
        },
    }
    if account_now:
        deal, repriced = await _reprice(session, ctx)
        changes.update(_price_changes(vehicle, repriced))
    version = await bump_and_log(
        session, deal, cmd.actor, HistoryEvent.SUPPORT_DECIDED, changes=changes, reason=comment
    )
    await notifications.notify(
        session, NotifyEvent.SUPPORT_DECIDED, deal, cmd.actor, version=version,
        extra={"support_request": _notification_payload(updated, vehicle)},
    )
    return {"deal": await build_card(session, cmd.actor, ctx.deal_id)}


async def handle_apply_approved_support(
    cmd: ApplyApprovedSupportCommand, session: AsyncSession
) -> dict[str, Any]:
    """Account the approved amount of a position that the price does not reflect yet.

    After sending the price is not changed automatically; this is the dealer's explicit
    step. A DD goes through the normal reset to a draft, a DL through the change cycle.
    Accounting twice is impossible: only the not yet accounted rest is subtracted.
    """
    ctx = await load_for_mutation(session, cmd.actor, cmd.deal_id, cmd.if_match)
    _require_dealer_side(ctx)
    ctx.require(
        Action.APPLY_SUPPORT,
        "Нет неучтённой поддержки для применения",
        **await support_action_facts(session, ctx),
    )
    vehicle = active_vehicle(ctx, cmd.vehicle_id)
    unaccounted: Decimal = (await support_repo.unaccounted_by_vehicle(session, ctx.deal_id)).get(
        vehicle["id"], ZERO
    )
    if unaccounted <= 0:
        raise FastDealStateError("По этой позиции нет неучтённой поддержки")

    _, advanced = await _begin_dealer_change(session, ctx)
    await support_repo.account_approved_requests(session, vehicle["id"])
    deal, repriced = await _reprice(session, ctx)
    changes = {
        _key(vehicle, "support_accounted"): {"before": None, "after": wire(unaccounted)},
        **_price_changes(vehicle, repriced),
    }
    await bump_and_log(
        session, deal, cmd.actor, HistoryEvent.SUPPORT_ACCOUNTED, changes=changes, version=advanced
    )
    return {"deal": await build_card(session, cmd.actor, ctx.deal_id)}


# ------------------------------------------------------------------------- helpers

def _require_dealer_side(ctx: DealContext) -> None:
    if not is_dealer_side(ctx):
        raise FastDealAccessDeniedError("Поддержки доступны только дилеру сделки")


async def _begin_dealer_change(
    session: AsyncSession, ctx: DealContext
) -> tuple[Record, int | None]:
    """Open a price-changing support action: the DD resets, the DL dealer just edits.

    Returns the editable deal and the version that a reset (or the reopening of a refused
    deal) has already advanced, else ``None``: the command's own event then describes that
    version instead of bumping it a second time.
    """
    ctx.require(Action.EDIT)
    if ctx.party != Party.INITIATOR:
        return ctx.deal, None
    deal = await lifecycle.prepare_initiator_mutation(session, ctx)
    return deal, (deal["version"] if deal["version"] != ctx.deal["version"] else None)


async def _reprice(session: AsyncSession, ctx: DealContext) -> tuple[Record, dict[UUID, Record]]:
    """Reprice and rebase the terms; a DL dealer's change is compared with the sent state."""
    deal, vehicles = await pricing.refresh_deal_totals(session, ctx.deal_id)
    if ctx.party == Party.DEALER:
        deal, _ = await pending_changes.refresh_pending_changes(session, ctx.deal_id)
    return deal, {item["id"]: item for item in vehicles}


async def _applied_of(session: AsyncSession, ctx: DealContext, vehicle: Record) -> list[Record]:
    rows: list[Record] = await support_repo.list_applied_supports(session, ctx.deal_id)
    return [row for row in rows if row["fast_deal_vehicle_id"] == vehicle["id"]]


def _zero_amount_message(offer: support_rules.ProgramOffer, deal: Record) -> str:
    if offer.support_type == "down_payment_compensation" and deal.get("down_payment_percent") is None:
        return "Укажите аванс в условиях лизинга: поддержка аванса рассчитывается от него"
    return "Сумма поддержки по этой программе равна нулю"


def _validated_decision(cmd: DecideSupportCommand, request: Record) -> tuple[SupportRequestStatus, Decimal | None]:
    try:
        status = SupportRequestStatus(cmd.status)
    except ValueError as exc:
        raise FastDealValidationError("Неизвестное решение по запросу", field="status") from exc
    if status not in _DECISIONS:
        raise FastDealValidationError("Неизвестное решение по запросу", field="status")
    if request["status"] not in OPEN_REQUEST_STATUSES:
        raise FastDealStateError("Решение по запросу уже принято")
    if status == request["status"]:
        raise FastDealStateError("Запрос уже предварительно согласован")
    if status == SupportRequestStatus.CANCELLED:
        return status, None
    if cmd.decided_amount is None:
        if status == SupportRequestStatus.APPROVED:
            raise FastDealValidationError("Укажите согласованную сумму", field="decided_amount")
        return status, None
    return status, positive_money(cmd.decided_amount, field="decided_amount")


def _comment(value: str | None, *, field: str) -> str | None:
    text = (value or "").strip()
    if not text:
        return None
    if len(text) > _MAX_COMMENT_LENGTH:
        raise FastDealValidationError(
            f"Комментарий не должен быть длиннее {_MAX_COMMENT_LENGTH} символов", field=field
        )
    return text


def _key(vehicle: Record, name: str) -> str:
    return f"vehicle.{vehicle['id']}.{name}"


def _price_changes(before: Record, repriced: dict[UUID, Record]) -> Record:
    """Price effect of a support action on one position, keyed like other position changes."""
    after = repriced.get(before["id"])
    if after is None:
        return {}
    return {
        _key(before, name): change
        for name, change in field_changes(before, after, _PRICE_FIELDS).items()
    }


def _notification_payload(request: Record, vehicle: Record) -> Record:
    """JSON-safe facts of a request for the distributor's and the dealer's notices."""
    return {
        "id": str(request["id"]),
        "status": request["status"],
        "requested_amount": wire(request["requested_amount"]),
        "decided_amount": wire(request["decided_amount"]),
        "accounted_amount": wire(request["accounted_amount"]),
        "comment": request["comment"],
        "decision_comment": request["decision_comment"],
        "distributor_company_id": str(request["distributor_company_id"]),
        "fast_deal_vehicle_id": str(request["fast_deal_vehicle_id"]),
        "vin": vehicle["vin"],
        "vehicle_name": f"{vehicle['mark_name']} {vehicle['model_name']}",
    }
