"""Transactional leasing facts shared by the business entry points.

The parent application remains the notification aggregate even when a vehicle,
commercial proposal or per-company branch changed. No recipient is selected here.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time
from decimal import Decimal
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from application.notifications.events import normalize_notification_value
from infrastructure.repositories import application_repository as app_repo
from infrastructure.repositories import (
    leasing_company_application_repository as lca_repo,
)
from infrastructure.settings import settings


def reservation_expiry_timestamp(value: date | datetime | None) -> datetime | None:
    """The vehicle API reserves through the chosen day in the business zone.

    Unlike Exchange deadlines this API remains DATE-compatible; event facts
    carry its unambiguous end-of-day instant in UTC.
    """
    if value is None or isinstance(value, datetime):
        return value
    return datetime.combine(
        value,
        time.max,
        ZoneInfo(settings.notification_business_timezone),
    ).astimezone(UTC)


async def record_leasing_event(
    session: AsyncSession,
    *,
    application: dict[str, Any],
    event_type: str,
    actor_user_id: UUID | None = None,
    previous_values: dict[str, Any] | None = None,
    new_values: dict[str, Any] | None = None,
    payload: dict[str, Any] | None = None,
    occurrence_key: str | None = None,
) -> UUID | None:
    from application.notifications.events import record_notification_event

    application_id = UUID(str(application["id"]))
    # Tiny existing projections do not carry the display number. Read the
    # canonical parent in the same transaction, never invent a numeric ID.
    number = application.get("display_number")
    if number is None:
        parent = await app_repo.get_by_id(session, application_id)
        number = parent.get("display_number") if parent is not None else None
    before = normalize_notification_value(previous_values or {})
    after = normalize_notification_value(new_values or {})
    changed = {
        key for key in before.keys() | after.keys() if before.get(key) != after.get(key)
    }
    if (previous_values is not None or new_values is not None) and not changed:
        return None
    return await record_notification_event(
        session,
        event_type=event_type,
        entity_type="leasing_application",
        entity_id=application_id,
        aggregate_id=application_id,
        application_id=application_id,
        request_number=str(number if number is not None else application_id),
        actor_user_id=actor_user_id,
        previous_values={key: before.get(key) for key in sorted(changed)},
        new_values={key: after.get(key) for key in sorted(changed)},
        payload=payload,
        occurrence_key=occurrence_key,
    )


async def record_lca_transition(
    session: AsyncSession,
    *,
    application: dict[str, Any],
    link: dict[str, Any],
    new_status: str,
    actor_user_id: UUID | None,
) -> UUID | None:
    """A branch outcome is not a terminal transition of the whole application."""
    decision = new_status.startswith(("approved", "rejected"))
    return await record_leasing_event(
        session,
        application=application,
        event_type=(
            "leasing.company_decision_received"
            if decision
            else "leasing.application_status_changed"
        ),
        actor_user_id=actor_user_id,
        previous_values={"lca_status": link["status"]},
        new_values={"lca_status": new_status},
        payload={
            "leasing_company_id": link["leasing_company_id"],
            "leasing_company_application_id": link["id"],
        },
    )


async def record_company_assignments(
    session: AsyncSession,
    *,
    application: dict[str, Any],
    leasing_company_ids: list[UUID],
    actor_user_id: UUID | None,
) -> None:
    """Only persisted LCA links are assignments; draft company choices are not.

    Stable link identity makes repeated administrative assignment a no-op in
    the outbox, including HTTP retries and repeated selection of the same set.
    """
    for company_id in dict.fromkeys(leasing_company_ids):
        link = await lca_repo.get_link_for_app_and_lc(
            session,
            application_id=application["id"],
            leasing_company_id=company_id,
        )
        if link is None:
            continue
        await record_leasing_event(
            session,
            application=application,
            event_type="leasing.company_assigned",
            actor_user_id=actor_user_id,
            payload={
                "leasing_company_id": company_id,
                "leasing_company_application_id": link["id"],
            },
            occurrence_key=f"leasing.company_assigned:{link['id']}",
        )


def option_price_snapshot(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Only the option identity and public price; never dealer-only comments."""
    snapshots = [
        {
            key: (
                format(Decimal(str(item[key] or 0)).normalize(), "f")
                if key == "price"
                else item[key]
            )
            for key in ("equipment_code", "service_code", "name", "price")
            if key in item
        }
        for item in items
    ]
    return sorted(
        snapshots,
        key=lambda item: (
            str(item.get("equipment_code", "")),
            str(item.get("service_code", "")),
        ),
    )
