"""Reservation recovery is one business transaction, never a direct email."""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from application.notifications.leasing_events import (
    record_leasing_event,
    reservation_expiry_timestamp,
)
from domain.entities.application_vehicle import expired_reservation_status
from infrastructure.repositories import application_vehicle_repository as repo
from infrastructure.settings import settings


async def scan_leasing_reservation_deadlines(
    session: AsyncSession,
    now: datetime,
) -> int:
    count = 0
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("Reservation clock must be timezone-aware")
    before_date = now.astimezone(
        ZoneInfo(settings.notification_business_timezone)
    ).date()
    for reservation in await repo.claim_expired_reservations(session, before_date):
        expiration = reservation_expiry_timestamp(reservation["reserve_expires_at"])
        assert expiration is not None
        status = expired_reservation_status(
            application_status=reservation["application_status"],
            car_status=reservation["car_status"],
            reserve_expires_at=expiration,
            now=now,
        )
        if status is None:
            continue
        await repo.release_expired_reservation(session, reservation["id"])
        await record_leasing_event(
            session,
            application={
                "id": reservation["application_id"],
                "display_number": reservation["display_number"],
            },
            event_type="leasing.vehicle_reservation_expired",
            previous_values={
                "car_status": reservation["car_status"],
                "reserve_expires_at": expiration,
            },
            new_values={"car_status": status.value, "reserve_expires_at": None},
            payload={"application_vehicle_id": reservation["id"]},
            occurrence_key=(
                f"leasing.vehicle_reservation_expired:{reservation['id']}:"
                f"{expiration.astimezone(UTC).isoformat()}"
            ),
        )
        count += 1
    return count
