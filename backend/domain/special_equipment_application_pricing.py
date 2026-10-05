"""Pure rules for agreeing a requested special-equipment application price."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from uuid import UUID

from domain.errors import DomainError

MONEY_QUANT = Decimal("0.01")


class RequestedPriceWorkflowError(DomainError):
    """Stable business error exposed by the requested-price use case."""

    code: str

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class RequestedPriceApplicationNotFoundError(RequestedPriceWorkflowError):
    def __init__(self) -> None:
        super().__init__("APPLICATION_NOT_FOUND", "Лизинговая заявка не найдена")


class RequestedPriceItemNotFoundError(RequestedPriceWorkflowError):
    def __init__(self) -> None:
        super().__init__("ITEM_NOT_FOUND", "Позиция заявки не найдена")


class RequestedPriceItemApplicationMismatchError(RequestedPriceWorkflowError):
    def __init__(self) -> None:
        super().__init__(
            "ITEM_APPLICATION_MISMATCH",
            "Позиция не относится к указанной заявке",
        )


class ApplicationNotActiveForPriceError(RequestedPriceWorkflowError):
    def __init__(self) -> None:
        super().__init__(
            "APPLICATION_NOT_ACTIVE",
            "Цена может быть выставлена только для активной заявки",
        )


class LeasingCompanyAlreadyAssignedForPriceError(RequestedPriceWorkflowError):
    def __init__(self) -> None:
        super().__init__(
            "LEASING_COMPANY_ALREADY_ASSIGNED",
            "Лизинговая компания уже назначена",
        )


class NotApplicationDealerError(RequestedPriceWorkflowError):
    def __init__(self) -> None:
        super().__init__(
            "NOT_APPLICATION_DEALER",
            "Позиция принадлежит другому дилеру",
        )


class PriceNotPositiveError(RequestedPriceWorkflowError):
    def __init__(self) -> None:
        super().__init__("PRICE_NOT_POSITIVE", "Цена должна быть больше нуля")


class ItemNotPriceOnRequestError(RequestedPriceWorkflowError):
    def __init__(self) -> None:
        super().__init__(
            "ITEM_NOT_PRICE_ON_REQUEST",
            "Для позиции не требуется согласование цены",
        )


class PriceOnRequestPendingError(RequestedPriceWorkflowError):
    def __init__(self) -> None:
        super().__init__(
            "PRICE_ON_REQUEST_PENDING",
            "Сначала дилер должен выставить цену для всех позиций",
        )


@dataclass(frozen=True, slots=True)
class DealerPriceUpdate:
    agreed_price: Decimal
    total_price: Decimal
    price_status: str
    price_set_by: UUID
    price_set_at: datetime


@dataclass(frozen=True, slots=True)
class DealerPriceTransition:
    """Current locked state needed for one dealer price transition."""

    application_status: str
    leasing_company_assigned: bool
    seller_company_id: UUID | None
    item_role: str
    item_status: str
    price_status: str
    price_on_request: bool

    def apply(
        self,
        *,
        actor_company_id: UUID | None,
        actor_id: UUID,
        agreed_price: Decimal | None,
        changed_at: datetime,
    ) -> DealerPriceUpdate:
        if self.application_status != "active":
            raise ApplicationNotActiveForPriceError()
        if self.leasing_company_assigned:
            raise LeasingCompanyAlreadyAssignedForPriceError()
        if actor_company_id is None or self.seller_company_id != actor_company_id:
            raise NotApplicationDealerError()
        if (
            not self.price_on_request
            or self.item_role == "component"
            or self.item_status not in {"active", "reserved"}
            or self.price_status not in {"pending", "set"}
        ):
            raise ItemNotPriceOnRequestError()
        if agreed_price is None or not agreed_price.is_finite() or agreed_price <= 0:
            raise PriceNotPositiveError()
        try:
            normalized = agreed_price.quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)
        except InvalidOperation as exc:
            raise PriceNotPositiveError() from exc
        if normalized <= 0:
            raise PriceNotPositiveError()
        return DealerPriceUpdate(
            agreed_price=normalized,
            total_price=normalized,
            price_status="set",
            price_set_by=actor_id,
            price_set_at=changed_at,
        )


def ensure_no_pending_requested_prices(items: list[dict[str, object]]) -> None:
    """Reject LC assignment while a current billable item waits for a price."""

    if any(
        item.get("price_status") == "pending"
        and item.get("item_role") != "component"
        and item.get("item_status") in {"active", "reserved"}
        for item in items
    ):
        raise PriceOnRequestPendingError()


__all__ = [
    "ApplicationNotActiveForPriceError",
    "DealerPriceTransition",
    "DealerPriceUpdate",
    "ItemNotPriceOnRequestError",
    "LeasingCompanyAlreadyAssignedForPriceError",
    "NotApplicationDealerError",
    "PriceNotPositiveError",
    "PriceOnRequestPendingError",
    "RequestedPriceApplicationNotFoundError",
    "RequestedPriceItemApplicationMismatchError",
    "RequestedPriceItemNotFoundError",
    "RequestedPriceWorkflowError",
    "ensure_no_pending_requested_prices",
]
