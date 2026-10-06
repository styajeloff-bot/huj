"""Pure state machine of the deal and of a leasing company invitation."""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from domain.fast_deals.errors import FastDealStateError
from domain.fast_deals.values import (
    FINAL_STATUSES,
    DealStatus,
    LcStatus,
    SourceType,
)

_S = DealStatus

_COMMON = {
    # The initiator corrects a refused deal: it returns to a draft.
    (_S.REJECTED, _S.DRAFT),
}
_DD = {
    (_S.DRAFT, _S.PENDING_LC_CONFIRMATION),
    (_S.PENDING_LC_CONFIRMATION, _S.PENDING_LC_FINAL_CONFIRMATION),
    (_S.PENDING_LC_FINAL_CONFIRMATION, _S.PENDING_LC_CONFIRMATION),
    (_S.PENDING_LC_FINAL_CONFIRMATION, _S.CONFIRMED),
    (_S.PENDING_LC_CONFIRMATION, _S.REJECTED),
    (_S.PENDING_LC_FINAL_CONFIRMATION, _S.REJECTED),
    (_S.PENDING_LC_CONFIRMATION, _S.DRAFT),
    (_S.PENDING_LC_FINAL_CONFIRMATION, _S.DRAFT),
}
_DL = {
    (_S.DRAFT, _S.PENDING_DEALER_CONFIRMATION),
    (_S.PENDING_DEALER_CONFIRMATION, _S.CONFIRMED),
    (_S.PENDING_DEALER_CONFIRMATION, _S.PENDING_LC_CHANGES_CONFIRMATION),
    (_S.PENDING_LC_CHANGES_CONFIRMATION, _S.CONFIRMED),
    (_S.PENDING_LC_CHANGES_CONFIRMATION, _S.REJECTED),
    (_S.PENDING_DEALER_CONFIRMATION, _S.REJECTED),
}
_TRANSITIONS: dict[SourceType, set[tuple[DealStatus, DealStatus]]] = {
    SourceType.DEALER_TO_LEASING: _DD | _COMMON,
    SourceType.LEASING_TO_DEALER: _DL | _COMMON,
}


def can_transition(source: SourceType | str, current: str, target: str) -> bool:
    """Cancellation is possible from any non-final status of either direction."""
    current_status, target_status = DealStatus(current), DealStatus(target)
    if current_status in FINAL_STATUSES:
        return False
    if target_status == DealStatus.CANCELLED:
        return True
    return (current_status, target_status) in _TRANSITIONS[SourceType(source)]


def require_transition(source: SourceType | str, current: str, target: str) -> None:
    if not can_transition(source, current, target):
        raise FastDealStateError(
            f"Сделка не может перейти из статуса «{current}» в «{target}»"
        )


def require_status(deal: Mapping[str, Any], *allowed: DealStatus, action: str = "") -> None:
    if deal["status"] not in {status.value for status in allowed}:
        suffix = f": {action}" if action else ""
        raise FastDealStateError(f"Действие недоступно в текущем статусе сделки{suffix}")


def is_final(status: str) -> bool:
    return DealStatus(status) in FINAL_STATUSES


# ---------------------------------------------------------------- leasing invitations

def restored_lc_status(application: Mapping[str, Any]) -> LcStatus:
    """After a selection is withdrawn or refused: a valid offer stays selectable.

    An invitation without an offer returns to review; a refusal is never revived.
    """
    if application["status"] == LcStatus.REJECTED:
        return LcStatus.REJECTED
    if application.get("current_offer_id"):
        return LcStatus.OFFER_SENT
    return LcStatus.PENDING_REVIEW


def remaining_after_refusal(applications: Iterable[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    """Invitations of the current cycle that can still deliver an answer."""
    return [
        application
        for application in applications
        if application["archived_at"] is None
        and application["status"]
        in {
            LcStatus.PENDING_REVIEW,
            LcStatus.OFFER_SENT,
            LcStatus.CLOSED_NOT_SELECTED,
            LcStatus.SELECTED_BY_DEALER,
        }
    ]
