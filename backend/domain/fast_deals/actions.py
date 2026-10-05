"""Server-side computation of the actions available to one actor on one deal.

The UI labels and enables its buttons from this list; the server re-checks every
request with the same function.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from domain.fast_deals.errors import FastDealStateError
from domain.fast_deals.values import (
    DealStatus,
    LcStatus,
    Party,
    SourceType,
)


class Action(StrEnum):
    EDIT = "edit"
    DELETE = "delete"
    CANCEL = "cancel"
    SEND_TO_LEASING_COMPANIES = "send_to_leasing_companies"
    SEND_TO_DEALERS = "send_to_dealers"
    SUBMIT_OFFER = "submit_offer"
    REJECT_AS_LEASING = "reject_as_leasing"
    SELECT_OFFER = "select_offer"
    WITHDRAW_SELECTION = "withdraw_selection"
    CONFIRM_AS_LEASING = "confirm_as_leasing"
    CONFIRM_AS_DEALER = "confirm_as_dealer"
    REJECT_AS_DEALER = "reject_as_dealer"
    SEND_CHANGES = "send_changes"
    ACCEPT_CHANGES = "accept_changes"
    REJECT_CHANGES = "reject_changes"
    UPLOAD_FILES = "upload_files"
    ASSIGN_EMPLOYEES = "assign_employees"
    REQUEST_SUPPORT = "request_support"
    APPLY_SUPPORT = "apply_support"
    DECIDE_SUPPORT = "decide_support"


@dataclass(frozen=True)
class ActionContext:
    """Facts besides the deal row that the rules need."""

    party: Party
    is_company_admin: bool = False
    # The actor's own invitation in the current cycle (leasing company in DD).
    lc_application: Mapping[str, Any] | None = None
    # Current-cycle invitations (the dealer's and the platform's view of DD).
    lc_applications: Sequence[Mapping[str, Any]] = ()
    active_vehicles: int = 0
    has_unaccounted_support: bool = False
    # Distributor: open support requests addressed to this company.
    open_support_requests: int = 0
    # Dealer: at least one position whose brand has a linked distributor.
    can_request_support: bool = False


def allowed_actions(deal: Mapping[str, Any], ctx: ActionContext) -> list[Action]:
    status = DealStatus(deal["status"])
    final = status in {DealStatus.CONFIRMED, DealStatus.CANCELLED}
    actions: list[Action] = []

    if ctx.is_company_admin and ctx.party in {
        Party.INITIATOR, Party.LEASING, Party.DEALER,
    }:
        # An administrative exception: reassignment is possible in any status.
        actions.append(Action.ASSIGN_EMPLOYEES)

    if ctx.party == Party.DISTRIBUTOR:
        if ctx.open_support_requests and not final:
            actions.append(Action.DECIDE_SUPPORT)
        return actions
    if ctx.party in {Party.PLATFORM, Party.NONE} or final:
        return actions

    if ctx.party == Party.INITIATOR:
        actions.extend(_initiator_actions(deal, status, ctx))
    elif ctx.party == Party.LEASING:
        actions.extend(_leasing_actions(status, ctx))
    elif ctx.party == Party.DEALER:
        actions.extend(_dealer_actions(deal, status, ctx))
    return actions


def _initiator_actions(
    deal: Mapping[str, Any], status: DealStatus, ctx: ActionContext
) -> list[Action]:
    dd = deal["source_type"] == SourceType.DEALER_TO_LEASING
    actions = [Action.CANCEL, Action.UPLOAD_FILES]
    if status in {DealStatus.DRAFT, DealStatus.REJECTED}:
        actions.append(Action.EDIT)
        if status == DealStatus.DRAFT and deal.get("sent_at") is None:
            actions.append(Action.DELETE)
        if status == DealStatus.DRAFT and ctx.active_vehicles > 0:
            actions.append(
                Action.SEND_TO_LEASING_COMPANIES if dd else Action.SEND_TO_DEALERS
            )
    if not dd:
        if status == DealStatus.PENDING_LC_CHANGES_CONFIRMATION:
            actions.extend([Action.ACCEPT_CHANGES, Action.REJECT_CHANGES])
        return actions
    # DD: dealer.
    if status in {
        DealStatus.PENDING_LC_CONFIRMATION,
        DealStatus.PENDING_LC_FINAL_CONFIRMATION,
    }:
        actions.append(Action.EDIT)  # a business change resets the deal to a draft
    if status == DealStatus.PENDING_LC_CONFIRMATION and any(
        item["status"] == LcStatus.OFFER_SENT and item["archived_at"] is None
        for item in ctx.lc_applications
    ):
        actions.append(Action.SELECT_OFFER)
    if status == DealStatus.PENDING_LC_FINAL_CONFIRMATION:
        actions.append(Action.WITHDRAW_SELECTION)
    if ctx.can_request_support:
        actions.append(Action.REQUEST_SUPPORT)
    if ctx.has_unaccounted_support:
        actions.append(Action.APPLY_SUPPORT)
    return actions


def _leasing_actions(status: DealStatus, ctx: ActionContext) -> list[Action]:
    application = ctx.lc_application
    if application is None or application["archived_at"] is not None:
        return []
    actions = [Action.UPLOAD_FILES]
    lc_status = LcStatus(application["status"])
    if status == DealStatus.PENDING_LC_CONFIRMATION:
        if lc_status == LcStatus.PENDING_REVIEW:
            actions.extend([Action.SUBMIT_OFFER, Action.REJECT_AS_LEASING])
        elif lc_status == LcStatus.OFFER_SENT:
            actions.append(Action.REJECT_AS_LEASING)
    elif (
        status == DealStatus.PENDING_LC_FINAL_CONFIRMATION
        and lc_status == LcStatus.SELECTED_BY_DEALER
    ):
        actions.extend([Action.CONFIRM_AS_LEASING, Action.REJECT_AS_LEASING])
    return actions


def _dealer_actions(
    deal: Mapping[str, Any], status: DealStatus, ctx: ActionContext
) -> list[Action]:
    actions = [Action.UPLOAD_FILES]
    if status != DealStatus.PENDING_DEALER_CONFIRMATION:
        return actions
    actions.extend([Action.EDIT, Action.REJECT_AS_DEALER])
    if deal["has_pending_changes"]:
        actions.append(Action.SEND_CHANGES)
    else:
        actions.append(Action.CONFIRM_AS_DEALER)
    if ctx.can_request_support:
        actions.append(Action.REQUEST_SUPPORT)
    if ctx.has_unaccounted_support:
        actions.append(Action.APPLY_SUPPORT)
    return actions


def require_action(actions: Sequence[Action], action: Action, message: str | None = None) -> None:
    """Raise a state error when the server does not allow the action."""
    if action not in actions:
        raise FastDealStateError(message or "Действие недоступно в текущем состоянии сделки")
