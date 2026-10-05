"""ExchangeRequest aggregate root — exchange subsystem (Phase 5 E2).

An exchange request is posted by a leasing company (LC) and visible to
dealers that are bound to the targeted warehouses. Dealers respond with
``ExchangeBid`` rows; the LC either confirms a bid (``deal``) or archives
the request.

Status machine
--------------

::

    open ───► deal                       (LC confirmed a dealer bid)
    open ───► archived                   (LC closed the request)
    deal ───► archived                   (post-deal cleanup)

``open`` is the initial status after ``submitCart``; requests are never
re-opened once moved away (they can only be resubmitted as brand-new
records by the LC).
"""
from __future__ import annotations

from dataclasses import dataclass, field, fields
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from domain.errors import (
    ExchangeRequestAccessDeniedError,
    InvalidExchangeRequestStatusError,
)

# ---------------------------------------------------------------------------
# Status constants
# ---------------------------------------------------------------------------

STATUS_OPEN = "open"
STATUS_DEAL = "deal"
STATUS_ARCHIVED = "archived"

ALL_STATUSES: frozenset[str] = frozenset(
    {STATUS_OPEN, STATUS_DEAL, STATUS_ARCHIVED}
)

_TRANSITIONS: dict[str, frozenset[str]] = {
    STATUS_OPEN: frozenset({STATUS_DEAL, STATUS_ARCHIVED}),
    STATUS_DEAL: frozenset({STATUS_ARCHIVED}),
    STATUS_ARCHIVED: frozenset(),
}


def _to_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (ValueError, ArithmeticError, TypeError):
        return None


def _to_opt_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _to_opt_uuid(value: Any) -> UUID | None:
    if value is None:
        return None
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        return None


def _to_int(value: Any, default: int = 0) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


@dataclass
class ExchangeRequest:
    """Aggregate root for a single exchange request."""

    id: UUID = field(default_factory=lambda: UUID(int=0))
    lc_user_id: UUID = field(default_factory=lambda: UUID(int=0))
    lc_company_id: UUID | None = None
    vehicle_id: UUID = field(default_factory=lambda: UUID(int=0))
    quantity: int = 1
    status: str = STATUS_OPEN
    accepted_bid_id: UUID | None = None
    discount_type: str | None = None
    discount_value: Decimal | None = None
    file_url: str | None = None
    file_name: str | None = None
    batch_number: int | None = None
    batch_index: int | None = None
    expiration_at: datetime | None = None
    dealer_ids: list[UUID] = field(default_factory=list)

    # ------------------------------------------------------------------
    # Hydration
    # ------------------------------------------------------------------

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ExchangeRequest:
        names = {f.name for f in fields(cls)}
        cleaned: dict[str, Any] = {}
        for key, raw in data.items():
            if key not in names:
                continue
            if key == "discount_value":
                cleaned[key] = _to_decimal(raw)
            elif key == "quantity":
                cleaned[key] = _to_int(raw, default=1)
            elif key == "status":
                cleaned[key] = str(raw) if raw is not None else STATUS_OPEN
            elif key == "dealer_ids":
                if raw is None:
                    cleaned[key] = []
                else:
                    cleaned[key] = [UUID(str(v)) for v in raw]
            elif key in {"id", "lc_user_id", "vehicle_id"}:
                cleaned[key] = UUID(str(raw)) if raw is not None else UUID(int=0)
            elif key in {"accepted_bid_id", "lc_company_id"}:
                cleaned[key] = _to_opt_uuid(raw)
            elif key in {"batch_number", "batch_index"}:
                cleaned[key] = _to_opt_int(raw)
            else:
                cleaned[key] = raw
        return cls(**cleaned)

    # ------------------------------------------------------------------
    # Authorization
    # ------------------------------------------------------------------

    def ensure_owned_by_lc(self, lc_user_id: UUID, company_id: UUID | None = None) -> None:
        """Membership/permissions are checked by the application policy."""
        if self.lc_company_id is not None:
            allowed = self.lc_company_id == company_id
        else:
            allowed = self.lc_user_id == lc_user_id
        if not allowed:
            raise ExchangeRequestAccessDeniedError()

    def ensure_not_expired(self, now: datetime | None = None) -> None:
        if self.expiration_at is not None and self.expiration_at <= (now or datetime.now(UTC)):
            raise InvalidExchangeRequestStatusError("Срок действия заявки истёк")

    def ensure_dealer_has_access(self, dealer_id: UUID) -> None:
        """Require the actor to be a dealer assigned to this request.

        Dealer-access is determined by ``exchange_request_warehouses.dealer_id``
        being resolved and passed in via ``dealer_ids``.
        """
        if dealer_id not in self.dealer_ids:
            raise ExchangeRequestAccessDeniedError()

    # ------------------------------------------------------------------
    # Status guards
    # ------------------------------------------------------------------

    def ensure_can_change_status(self, new_status: str) -> None:
        if new_status not in ALL_STATUSES:
            raise InvalidExchangeRequestStatusError(
                f"Недопустимый переход: {self.status} → {new_status}"
            )
        if new_status == self.status:
            raise InvalidExchangeRequestStatusError(
                f"Недопустимый переход: {self.status} → {new_status}"
            )
        if new_status not in _TRANSITIONS.get(self.status, frozenset()):
            raise InvalidExchangeRequestStatusError(
                f"Недопустимый переход: {self.status} → {new_status}"
            )

    def ensure_can_accept_bid(self) -> None:
        """LC can accept a bid only while the request is still open."""
        self.ensure_not_expired()
        if self.status != STATUS_OPEN:
            raise InvalidExchangeRequestStatusError(
                "Сделку можно оформить только для открытой заявки"
            )
        if self.accepted_bid_id is not None:
            raise InvalidExchangeRequestStatusError(
                "По заявке биржи уже принята другая ставка"
            )

    def ensure_can_archive(self) -> None:
        if self.status == STATUS_ARCHIVED:
            raise InvalidExchangeRequestStatusError(
                "Заявка уже в архиве"
            )

    def ensure_can_receive_bid(self) -> None:
        """Dealers may only bid while the request is still open."""
        self.ensure_not_expired()
        if self.status != STATUS_OPEN:
            raise InvalidExchangeRequestStatusError(
                "Нельзя сделать ставку на закрытую заявку"
            )

    def ensure_can_submit(self) -> None:
        """LC may submit (move cart → open) only while in open status.

        For this migration, creating a request directly persists it with
        ``open`` status — a subsequent ``submit`` call is a no-op unless
        the row is still editable.
        """
        if self.status != STATUS_OPEN:
            raise InvalidExchangeRequestStatusError(
                "Отправить дилерам можно только открытую заявку"
            )
