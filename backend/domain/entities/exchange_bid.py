"""ExchangeBid aggregate root — exchange subsystem (Phase 5 E2).

A dealer posts one bid per exchange request. The bid carries a price and
optional comment; the LC may send a KP (commercial proposal) document to
the dealer, who either accepts or rejects. ``is_accepted`` is flipped by
the LC when confirming a deal.

KP status machine
-----------------

::

    none ───► sent           (LC uploads KP document for this bid)
    sent ───► accepted       (dealer accepts KP)
    sent ───► rejected       (dealer rejects KP)
    accepted ───► (terminal — LC can confirm deal)
    rejected ───► (terminal — LC may reopen by re-sending KP; no transition here)

``approve`` / ``reject`` in the Phase 5 API surface correspond to the LC
decision to confirm or discard a bid. In the Express implementation
``approve`` sets ``is_accepted=true`` + moves the request to ``deal``;
``reject`` archives the bid by leaving its KP flow untouched and signaling
rejection at the request level. Both only legitimate on bids whose KP has
been accepted by the dealer.
"""
from __future__ import annotations

from dataclasses import dataclass, field, fields
from decimal import Decimal
from typing import Any
from uuid import UUID

from domain.errors import (
    BidAlreadyAcceptedError,
    ExchangeBidAccessDeniedError,
    InvalidBidStatusError,
)

# ---------------------------------------------------------------------------
# KP status constants
# ---------------------------------------------------------------------------

KP_NONE = "none"
KP_SENT = "sent"
KP_ACCEPTED = "accepted"
KP_REJECTED = "rejected"

ALL_KP_STATUSES: frozenset[str] = frozenset(
    {KP_NONE, KP_SENT, KP_ACCEPTED, KP_REJECTED}
)


def _to_decimal(value: Any, default: Decimal = Decimal("0")) -> Decimal:
    if value is None:
        return default
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (ValueError, ArithmeticError, TypeError):
        return default


def _to_int(value: Any, default: int = 0) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


@dataclass
class ExchangeBid:
    """Aggregate root for a dealer bid on an exchange request."""

    id: UUID = field(default_factory=lambda: UUID(int=0))
    request_id: UUID = field(default_factory=lambda: UUID(int=0))
    dealer_id: UUID = field(default_factory=lambda: UUID(int=0))
    price: Decimal = Decimal("0")
    quantity: int = 1
    comment: str | None = None
    is_accepted: bool = False
    kp_status: str = KP_NONE
    kp_file_url: str | None = None
    kp_file_name: str | None = None
    kp_dealer_comment: str | None = None
    bid_file_url: str | None = None
    bid_file_name: str | None = None

    # ------------------------------------------------------------------
    # Hydration
    # ------------------------------------------------------------------

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ExchangeBid:
        names = {f.name for f in fields(cls)}
        cleaned: dict[str, Any] = {}
        for key, raw in data.items():
            if key not in names:
                continue
            if key == "price":
                cleaned[key] = _to_decimal(raw)
            elif key == "quantity":
                cleaned[key] = _to_int(raw, default=1)
            elif key in {"id", "request_id", "dealer_id"}:
                cleaned[key] = UUID(str(raw)) if raw is not None else UUID(int=0)
            elif key == "is_accepted":
                cleaned[key] = bool(raw)
            elif key == "kp_status":
                cleaned[key] = str(raw) if raw is not None else KP_NONE
            else:
                cleaned[key] = raw
        return cls(**cleaned)

    # ------------------------------------------------------------------
    # Authorization
    # ------------------------------------------------------------------

    def ensure_owned_by_dealer(self, dealer_id: UUID) -> None:
        if self.dealer_id != dealer_id:
            raise ExchangeBidAccessDeniedError()

    # ------------------------------------------------------------------
    # Domain invariants
    # ------------------------------------------------------------------

    def ensure_valid_price(self) -> None:
        if self.price <= Decimal("0"):
            raise InvalidBidStatusError("Цена ставки должна быть положительной")

    def ensure_quantity_in_range(self, max_quantity: int) -> None:
        if self.quantity < 1:
            raise InvalidBidStatusError("Количество должно быть минимум 1")
        if max_quantity >= 1 and self.quantity > max_quantity:
            # Clamp on caller side; defensive check here.
            raise InvalidBidStatusError(
                f"Количество не может превышать {max_quantity}"
            )

    # ------------------------------------------------------------------
    # KP status guards
    # ------------------------------------------------------------------

    def ensure_can_respond_to_kp(self) -> None:
        """Dealer responds (accept/reject) only when KP is in ``sent`` state."""
        if self.kp_status != KP_SENT:
            raise InvalidBidStatusError(
                "Нет КП для ответа или оно уже обработано"
            )

    def ensure_can_approve(self) -> None:
        """LC approves (confirms deal on) a bid.

        KP flow is optional — the LC can close the deal on any bid that has
        not yet been accepted. The old "KP accepted by dealer" precondition
        was dropped per product request.
        """
        if self.is_accepted:
            raise InvalidBidStatusError("Ставка уже принята")

    def ensure_can_reject(self) -> None:
        """LC may reject an active bid regardless of KP state (pre-deal)."""
        if self.is_accepted:
            raise InvalidBidStatusError(
                "Нельзя отклонить уже принятую ставку"
            )

    def ensure_can_withdraw(self) -> None:
        """An accepted bid remains the immutable basis of the confirmed deal."""
        if self.is_accepted:
            raise BidAlreadyAcceptedError()

    # ------------------------------------------------------------------
    # Mutations
    # ------------------------------------------------------------------

    def mark_kp_sent(self) -> None:
        self.kp_status = KP_SENT
        self.kp_dealer_comment = None

    def mark_kp_accepted(self, *, comment: str | None = None) -> None:
        self.ensure_can_respond_to_kp()
        self.kp_status = KP_ACCEPTED
        self.kp_dealer_comment = comment

    def mark_kp_rejected(self, *, comment: str | None = None) -> None:
        self.ensure_can_respond_to_kp()
        self.kp_status = KP_REJECTED
        self.kp_dealer_comment = comment

    def mark_accepted(self) -> None:
        self.ensure_can_approve()
        self.is_accepted = True
