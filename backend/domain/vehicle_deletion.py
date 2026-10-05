"""Vehicle deletion confirmation and dependency vocabulary."""
from dataclasses import dataclass
from typing import TypedDict

from domain.errors import DomainError


class BlockingReason(TypedDict):
    type: str
    count: int
    description: str


class VehicleDeletionBlockedError(DomainError):
    def __init__(self, blocking_reasons: tuple[BlockingReason, ...]) -> None:
        super().__init__("Автомобиль имеет блокирующие связи")
        self.blocking_reasons = list(blocking_reasons)


@dataclass(frozen=True)
class VehicleDeletionPolicy:
    """The same dependency rule governs advisory checks and locked deletion."""

    blocking_reasons: tuple[BlockingReason, ...]

    @property
    def can_delete(self) -> bool:
        return not self.blocking_reasons

    def assert_allowed(self) -> None:
        if not self.can_delete:
            raise VehicleDeletionBlockedError(self.blocking_reasons)


BLOCKING_RELATIONS = {
    "leasing_applications": "Лизинговые заявки",
    "application_vehicles": "Автомобили в составе заявок",
    "application_vehicle_allocations": (
        "Подбор автомобилей в заявках и быстрых сделках, включая историю"
    ),
    "fast_deal_vehicles": "Позиции быстрых сделок, включая историю",
    "purchase_orders": "Заказы на покупку, включая отменённые",
    "exchange_requests": "Запросы биржи",
    "shopping_cart": "Корзины пользователей",
    "user_favorites": "Избранное пользователей",
    "exchange_cart_items": "Корзины биржи",
    "compensations": "Компенсации",
    "application_applied_supports": "Применённые меры поддержки",
    "leasing_application_vehicle_calculations": "Расчёты автомобилей заявок",
    "calculation_history": "История расчётов",
    "guest_cart_transfers": "Переносы гостевых корзин",
}


def confirmation_matches(confirmation: str | None, vin: str = "") -> bool:
    return confirmation == "УДАЛИТЬ" or bool(vin and confirmation == vin)
