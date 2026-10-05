"""Permissions for operations that still affect an entire commercial line."""

from uuid import UUID

from domain.dealer_distribution import DealerDistributionConflictError
from domain.errors import ApplicationNotOwnedError


def can_manage_whole_vehicle(
    *, actor_role: str, actor_company_id: UUID | None,
    stock_owner_id: UUID | None, quantity: int,
    distributed_quantity: int, actor_quantity: int,
) -> bool:
    """A partial recipient cannot mutate another dealer's portion."""
    return (
        actor_role == "carcraft_employee"
        or distributed_quantity == 0
        or (actor_company_id is not None and actor_company_id == stock_owner_id)
        or (actor_role == "dealer" and actor_quantity == quantity)
    )


def ensure_whole_vehicle_write(*, allowed: bool) -> None:
    if not allowed:
        raise ApplicationNotOwnedError(
            "Дилеру назначена часть количества. Изменять всю позицию может владелец склада"
        )


def ensure_distributed_quantity_retained(*, distributed_quantity: int, quantity: int) -> None:
    if quantity < distributed_quantity:
        raise DealerDistributionConflictError(
            "Количество не может быть меньше уже распределённого между дилерами"
        )
