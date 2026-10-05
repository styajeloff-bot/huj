"""Dealer report — dealer-owned data or employee overrides."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from domain.errors import InvalidDateRangeError, ReportsAccessDeniedError
from infrastructure.repositories import reporting_repository as repo


@dataclass
class GetDealerReportQuery:
    actor_id: UUID
    actor_role: str
    dealer_id: UUID | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None


def _ensure_range(date_from: datetime | None, date_to: datetime | None) -> None:
    for value in (date_from, date_to):
        if value is not None and value.tzinfo is None:
            raise InvalidDateRangeError(
                "Даты должны быть в формате ISO-8601 с указанием таймзоны"
            )
    if date_from is not None and date_to is not None and date_from > date_to:
        raise InvalidDateRangeError(
            "Начало периода не может быть позже конца"
        )


def resolve_dealer_id(
    *,
    actor_id: UUID,
    actor_role: str,
    requested_dealer_id: UUID | None,
) -> UUID:
    if actor_role == "carcraft_employee":
        return requested_dealer_id if requested_dealer_id else actor_id
    if actor_role == "dealer":
        # Dealers can only see their own report; requested_dealer_id is ignored.
        return actor_id
    raise ReportsAccessDeniedError(
        "Отчёт доступен только дилерам и сотрудникам Carcraft"
    )


async def handle_get_dealer_report(
    query: GetDealerReportQuery, session: AsyncSession
) -> dict[str, Any]:
    _ensure_range(query.date_from, query.date_to)
    dealer_id = resolve_dealer_id(
        actor_id=query.actor_id,
        actor_role=query.actor_role,
        requested_dealer_id=query.dealer_id,
    )
    overview = await repo.dealer_overview(
        session,
        dealer_id=dealer_id,
        date_from=query.date_from,
        date_to=query.date_to,
    )
    applications = await repo.dealer_applications(
        session,
        dealer_id=dealer_id,
        date_from=query.date_from,
        date_to=query.date_to,
    )
    status_distribution = await repo.dealer_status_distribution(
        session,
        dealer_id=dealer_id,
        date_from=query.date_from,
        date_to=query.date_to,
    )
    timeline = await repo.dealer_timeline(
        session,
        dealer_id=dealer_id,
        date_from=query.date_from,
        date_to=query.date_to,
        granularity="month",
    )
    return {
        "dealer_id": dealer_id,
        "overview": overview,
        "applications": applications,
        "status_distribution": status_distribution,
        "timeline": timeline,
    }
