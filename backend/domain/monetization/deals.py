"""Pure state transitions of immutable internal financial snapshots."""

from copy import deepcopy
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from domain.monetization.errors import (
    MonetizationAccessDenied,
    MonetizationConflict,
    MonetizationValidation,
)
from domain.monetization.terms import apply_terms


def required_confirmations(deal: dict[str, Any]) -> list[str]:
    """Leasing and dealer always confirm; distributor only when actually applied."""
    required = ["leasing", "dealer"]
    if any(row["participant_type"] == "distributor" for row in deal["amounts"]):
        required.append("distributor")
    return required


def validate_confirmation(deal: dict[str, Any], role: str) -> None:
    """Reject duplicate, inapplicable and premature final confirmations."""
    if deal["status"] != "pending_approval":
        raise MonetizationConflict(
            "Подтвердить можно только сделку, ожидающую согласования"
        )
    applicable = required_confirmations(deal)
    if role not in [*applicable, "admin"]:
        raise MonetizationAccessDenied(
            "Эта сторона не участвует в подтверждении сделки"
        )
    confirmations = deal.get("confirmations", {})
    if confirmations.get(role):
        raise MonetizationConflict("Эта сторона уже подтвердила сделку")
    if role == "admin":
        missing = [
            side
            for side in applicable
            if not confirmations.get(side)
            or confirmations[side].get("revision") != deal["revision"]
        ]
        if missing:
            raise MonetizationConflict(
                f"Ожидаются подтверждения: {', '.join({'leasing': 'ЛК', 'dealer': 'дилер', 'distributor': 'дистрибьютор'}[side] for side in missing)}"
            )


def confirm_deal(
    deal: dict[str, Any],
    role: str,
    user_id: UUID,
    confirmed_at: datetime,
) -> dict[str, Any]:
    """Record a participant confirmation or final administrative confirmation."""
    validate_confirmation(deal, role)
    _validate_actor(user_id, confirmed_at)
    updated = deepcopy(deal)
    updated.setdefault("confirmations", {})[role] = {
        "user_id": user_id,
        "confirmed_at": confirmed_at,
        "revision": deal["revision"],
    }
    if role == "admin":
        updated["status"] = "paid"
    return updated


def _validate_actor(user_id: UUID, timestamp: datetime) -> None:
    if not isinstance(user_id, UUID):
        raise MonetizationValidation("Укажите UUID пользователя, выполняющего действие")
    if not isinstance(timestamp, datetime) or timestamp.utcoffset() is None:
        raise MonetizationValidation(
            "Время финансового действия должно содержать часовой пояс"
        )


def adjust_deal(
    deal: dict[str, Any],
    changes: list[dict[str, Any]],
    user_id: UUID,
    changed_at: datetime,
) -> dict[str, Any]:
    """Apply an administrator's changes atomically; authorization belongs to the caller."""
    if deal["status"] != "pending_approval":
        raise MonetizationConflict(
            "Изменить суммы можно только в сделке, ожидающей согласования"
        )
    _validate_actor(user_id, changed_at)
    updated = deepcopy(deal)
    entries = apply_terms(updated, changes)
    if entries:
        updated["revision"] = deal["revision"] + 1
        updated["confirmations"] = {}
        updated.setdefault("adjustments", []).extend(
            dict(entry, id=uuid4(), changed_by=user_id, changed_at=changed_at)
            for entry in entries
        )
    return updated


def platform_auto_amount(amounts: list[dict[str, Any]]) -> Decimal:
    """Residual shown in the inline terms editor, without inventing a money row."""
    return sum(
        (
            row["amount"] if row["side"] == "expense" else -row["amount"]
            for row in amounts
            if row["side"] == "expense" or row["participant_type"] != "platform"
        ),
        Decimal("0"),
    )
