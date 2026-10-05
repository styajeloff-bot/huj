"""Leasing-company report — LC-owned data or employee overrides."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from domain.errors import InvalidDateRangeError, ReportsAccessDeniedError
from infrastructure.repositories import application_repository as app_repo
from infrastructure.repositories import reporting_repository as repo


@dataclass
class GetLeasingCompanyReportQuery:
    actor_id: UUID
    actor_role: str
    actor_company_id: UUID | None
    leasing_company_id: UUID | None = None
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


async def resolve_lc_id(
    session: AsyncSession,
    *,
    actor_role: str,
    actor_company_id: UUID | None,
    requested_lc_id: UUID | None,
) -> UUID:
    if actor_role == "carcraft_employee":
        if requested_lc_id is not None:
            return requested_lc_id
        raise ReportsAccessDeniedError(
            "Для сотрудника требуется указать leasing_company_id"
        )
    if actor_role == "leasing_company":
        resolved = await app_repo.resolve_leasing_company_id(
            session, actor_company_id
        )
        if resolved is None:
            raise ReportsAccessDeniedError(
                "Пользователь не привязан к лизинговой компании"
            )
        return cast("UUID", resolved)
    raise ReportsAccessDeniedError(
        "Отчёт доступен только лизинговой компании или сотруднику Carcraft"
    )


async def handle_get_leasing_company_report(
    query: GetLeasingCompanyReportQuery, session: AsyncSession
) -> dict[str, Any]:
    _ensure_range(query.date_from, query.date_to)
    lc_id = await resolve_lc_id(
        session,
        actor_role=query.actor_role,
        actor_company_id=query.actor_company_id,
        requested_lc_id=query.leasing_company_id,
    )
    overview = await repo.leasing_company_overview(
        session,
        leasing_company_id=lc_id,
        date_from=query.date_from,
        date_to=query.date_to,
    )
    applications = await repo.leasing_company_applications(
        session,
        leasing_company_id=lc_id,
        date_from=query.date_from,
        date_to=query.date_to,
    )
    status_distribution = await repo.leasing_company_status_distribution(
        session,
        leasing_company_id=lc_id,
        date_from=query.date_from,
        date_to=query.date_to,
    )
    timeline = await repo.leasing_company_timeline(
        session,
        leasing_company_id=lc_id,
        date_from=query.date_from,
        date_to=query.date_to,
        granularity="month",
    )
    return {
        "leasing_company_id": lc_id,
        "overview": overview,
        "applications": applications,
        "status_distribution": status_distribution,
        "timeline": timeline,
    }
