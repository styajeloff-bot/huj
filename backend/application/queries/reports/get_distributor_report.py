"""Distributor report — distributor-owned data or employee overrides."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from domain.errors import (
    DistributorScopeMissingError,
    InvalidDateRangeError,
    ReportsAccessDeniedError,
)
from infrastructure.repositories import reporting_repository as repo


@dataclass
class GetDistributorReportQuery:
    actor_id: UUID
    actor_role: str
    actor_company_id: UUID | None
    distributor_id: UUID | None = None
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


async def resolve_distributor_company_id(
    session: AsyncSession,
    *,
    actor_id: UUID,
    actor_role: str,
    actor_company_id: UUID | None,
    requested_distributor_id: UUID | None,
) -> UUID:
    if actor_role == "carcraft_employee":
        if requested_distributor_id is not None:
            return requested_distributor_id
        if actor_company_id is not None:
            return actor_company_id
        raise ReportsAccessDeniedError(
            "Для сотрудника требуется указать distributor_id"
        )
    if actor_role == "distributor":
        resolved = await repo.get_distributor_company_id_for_user(
            session, actor_id
        )
        if resolved is None:
            if actor_company_id is not None:
                return actor_company_id
            raise DistributorScopeMissingError()
        if not isinstance(resolved, UUID):
            raise TypeError("distributor company id must be a UUID")
        return resolved
    raise ReportsAccessDeniedError(
        "Отчёт доступен только дистрибьюторам и сотрудникам Carcraft"
    )


async def handle_get_distributor_report(
    query: GetDistributorReportQuery, session: AsyncSession
) -> dict[str, Any]:
    _ensure_range(query.date_from, query.date_to)
    distributor_company_id = await resolve_distributor_company_id(
        session,
        actor_id=query.actor_id,
        actor_role=query.actor_role,
        actor_company_id=query.actor_company_id,
        requested_distributor_id=query.distributor_id,
    )
    overview = await repo.distributor_overview(
        session,
        distributor_company_id=distributor_company_id,
        date_from=query.date_from,
        date_to=query.date_to,
    )
    applications = await repo.distributor_applications(
        session,
        distributor_company_id=distributor_company_id,
        date_from=query.date_from,
        date_to=query.date_to,
    )
    timeline = await repo.distributor_timeline(
        session,
        distributor_company_id=distributor_company_id,
        date_from=query.date_from,
        date_to=query.date_to,
        granularity="month",
    )
    return {
        "distributor_company_id": distributor_company_id,
        "overview": overview,
        "applications": applications,
        "timeline": timeline,
    }
