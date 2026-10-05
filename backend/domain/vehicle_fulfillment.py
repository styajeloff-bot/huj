"""Pure invariants for supplier quantities and physical-stock selection."""
from datetime import date
from typing import Any
from uuid import UUID

from domain.errors import (
    ApplicationVehicleAssignmentError,
    ApplicationVehicleFulfillmentRequiredError,
    VehicleNotAvailableError,
)


def ensure_fulfillment_request(*, quantity: int, vehicle_ids: list[UUID],
                              expires: date | None, today: date,
                              current_ids: set[UUID], comment: str | None) -> None:
    if not 1 <= quantity <= 2147483647:
        raise ApplicationVehicleAssignmentError("Количество должно быть от 1 до 2147483647")
    if len(vehicle_ids) > quantity:
        raise ApplicationVehicleAssignmentError("Количество выбранных машин превышает подтверждённое количество")
    if len(set(vehicle_ids)) != len(vehicle_ids):
        raise ApplicationVehicleAssignmentError("Одна машина не может быть выбрана дважды")
    if expires is None or expires < today:
        raise ApplicationVehicleAssignmentError("Укажите действующий срок бронирования")
    if current_ids and current_ids != set(vehicle_ids) and not (comment or "").strip():
        raise ApplicationVehicleAssignmentError("Укажите причину изменения подбора")


def ensure_stock_matches(*, vehicle: dict[str, Any], retained: bool, complectation_id: str | None) -> None:
    if complectation_id and vehicle.get("complectation_id") != complectation_id:
        raise ApplicationVehicleAssignmentError("Выберите машину той же комплектации")
    expected_status = "reserved" if retained else "available"
    if vehicle.get("status") != expected_status or not vehicle.get("is_available"):
        raise VehicleNotAvailableError(vehicle["id"])


def fulfillment_editable(*, actor_role: str, application_status: str | None,
                         line_status: str | None, has_lc_children: bool) -> bool:
    return actor_role in {"dealer", "distributor", "carcraft_employee"} and application_status == "active" \
        and line_status in {"active", "confirmed", "replacement"} and not has_lc_children


def ensure_dealer_action_uses_fulfillment(action: str) -> None:
    if action == "reserve":
        raise ApplicationVehicleFulfillmentRequiredError()
