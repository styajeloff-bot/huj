"""Business rules for vehicles included in leasing applications."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from domain.values import ApplicationVehicleStatus

DealerVehicleAction = Literal[
    "reject",
    "replace",
    "reserve",
    "discount",
    "markup",
    "contact_client",
    "replace_vin",
]


_TARGET_STATUS_BY_ACTION: dict[str, ApplicationVehicleStatus | None] = {
    "reject": ApplicationVehicleStatus.NOT_CONFIRMED,
    "replace": ApplicationVehicleStatus.REPLACEMENT,
    "reserve": ApplicationVehicleStatus.CONFIRMED,
    "discount": ApplicationVehicleStatus.CONFIRMED,
    "markup": None,
    "contact_client": None,
    "replace_vin": ApplicationVehicleStatus.REPLACEMENT,
}


def target_status_for_dealer_action(
    action: str,
) -> ApplicationVehicleStatus | None:
    """Return the vehicle status produced by a completed dealer action."""
    try:
        return _TARGET_STATUS_BY_ACTION[action]
    except KeyError:
        raise ValueError(f"unknown dealer vehicle action: {action}") from None


def expired_reservation_status(
    *, application_status: str, car_status: str,
    reserve_expires_at: datetime | None, now: datetime,
) -> ApplicationVehicleStatus | None:
    """Release only an expired confirmed reservation of an active application."""
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("Reservation clock must be timezone-aware")
    if reserve_expires_at is not None and (
        reserve_expires_at.tzinfo is None or reserve_expires_at.utcoffset() is None
    ):
        raise ValueError("Reservation expiry must be timezone-aware")
    if (
        application_status == "active"
        and car_status == ApplicationVehicleStatus.CONFIRMED
        and reserve_expires_at is not None
        and reserve_expires_at <= now
    ):
        return ApplicationVehicleStatus.PENDING_CONFIRMATION
    return None
