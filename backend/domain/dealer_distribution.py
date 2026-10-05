"""Pure invariants for distributing an application line's unassigned quantity."""

from dataclasses import dataclass
from typing import Any, Literal
from uuid import UUID

from domain.errors import (
    ApplicationNotOwnedError,
    ApplicationVehicleAssignmentError,
    DealerAssignmentNotAllowedError,
    DomainError,
)


class DealerDistributionConflictError(DomainError):
    """The requested remaining quantity or idempotency state is stale."""


@dataclass(frozen=True)
class DistributionItem:
    application_vehicle_id: UUID
    quantity: int
    expected_unassigned_quantity: int

    def ensure_valid(self) -> None:
        if type(self.quantity) is not int or self.quantity <= 0:
            raise ApplicationVehicleAssignmentError(
                "Количество должно быть положительным целым"
            )
        if (
            type(self.expected_unassigned_quantity) is not int
            or self.expected_unassigned_quantity < 0
        ):
            raise ApplicationVehicleAssignmentError(
                "Ожидаемый остаток должен быть целым неотрицательным"
            )


def ensure_distribution_actor(role: str, company_id: UUID | None) -> None:
    if role != "distributor" or company_id is None:
        raise ApplicationNotOwnedError(
            "Распределять автомобили может дистрибьютор с выбранной компанией"
        )


def ensure_distribution_items(items: tuple[DistributionItem, ...]) -> None:
    if not items or len(items) > 200:
        raise ApplicationVehicleAssignmentError("Выберите от 1 до 200 позиций заявки")
    if len({item.application_vehicle_id for item in items}) != len(items):
        raise ApplicationVehicleAssignmentError("Позиция заявки указана несколько раз")
    for item in items:
        item.ensure_valid()


def ensure_distribution_candidate(candidate: dict[str, Any] | None) -> None:
    if (
        not candidate
        or candidate["company_type"] != "dealer"
        or not candidate["is_active"]
    ):
        raise DealerAssignmentNotAllowedError(
            "Дилер не активен или не доступен текущему дистрибьютору"
        )


@dataclass(frozen=True)
class DistributionAvailability:
    unassigned_quantity: int
    blocked_reason: Literal["role", "stock_owner", "status", "quantity"] | None

    @property
    def can_assign_dealer(self) -> bool:
        return self.blocked_reason is None and self.unassigned_quantity > 0


def distribution_availability(
    *,
    actor_role: str,
    actor_company_id: UUID | None,
    stock_owner_id: UUID | None,
    quantity: int | None,
    distributed_quantity: int,
    legacy_dealer_assigned: bool,
    status: str | None,
    stock_owner_type: str | None = None,
) -> DistributionAvailability:
    """Use the same remaining stock and eligibility for display and allocation."""
    owns_stock = actor_company_id is not None and stock_owner_id == actor_company_id
    dealer_stock = stock_owner_type == "dealer"
    remaining = max(0, (quantity or 0) - distributed_quantity)
    if (
        legacy_dealer_assigned
        or dealer_stock
        or (actor_role == "dealer" and not owns_stock)
    ):
        remaining = 0
    reason: Literal["role", "stock_owner", "status", "quantity"] | None = None
    if actor_role != "distributor" or actor_company_id is None:
        reason = "role"
    elif not owns_stock or dealer_stock:
        reason = "stock_owner"
    elif status in {"removed", "replaced", "rejected"}:
        reason = "status"
    elif quantity is None or quantity <= 0:
        reason = "quantity"
    return DistributionAvailability(remaining, reason)


def ensure_distribution_quantity(
    item: DistributionItem,
    *,
    stock_owner_id: UUID | None,
    actor_company_id: UUID,
    quantity: int | None,
    distributed_quantity: int,
    legacy_dealer_assigned: bool,
    status: str | None,
) -> None:
    availability = distribution_availability(
        actor_role="distributor",
        actor_company_id=actor_company_id,
        stock_owner_id=stock_owner_id,
        quantity=quantity,
        distributed_quantity=distributed_quantity,
        legacy_dealer_assigned=legacy_dealer_assigned,
        status=status,
    )
    if availability.blocked_reason in {"role", "stock_owner"}:
        raise ApplicationNotOwnedError(
            "Распределять можно только автомобили со склада активного дистрибьютора"
        )
    if availability.blocked_reason == "status":
        raise DealerDistributionConflictError(
            "Позиция больше не доступна для распределения"
        )
    if availability.blocked_reason == "quantity":
        raise DealerDistributionConflictError("Количество позиции не определено")
    remaining = availability.unassigned_quantity
    if remaining != item.expected_unassigned_quantity:
        raise DealerDistributionConflictError(
            "Остаток изменился. Обновите заявку и повторите назначение"
        )
    if item.quantity > remaining:
        raise DealerDistributionConflictError(
            "Количество превышает неназначенный остаток"
        )
