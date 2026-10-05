"""Get admin dashboard stats (top-level KPIs)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.repositories import (
    admin_companies_repository as companies_repo,
)
from infrastructure.repositories import admin_stats_repository as stats_repo
from infrastructure.repositories import admin_users_repository as users_repo


@dataclass
class GetAdminStatsQuery:
    """Empty marker — stats are global."""


async def handle_get_admin_stats(
    _query: GetAdminStatsQuery,
    session: AsyncSession,
) -> dict[str, Any]:
    users_by_role = await users_repo.count_active_by_role(session)
    total_users = await users_repo.count_active_total(session)
    companies_by_type = (
        await companies_repo.count_active_companies_by_type(session)
    )
    total_companies = await companies_repo.count_active_companies_total(
        session
    )
    base = await stats_repo.aggregate_stats(session)

    return {
        "users_by_role": users_by_role,
        "total_users": total_users,
        "companies_by_type": companies_by_type,
        "total_companies": total_companies,
        "applications_by_status": base["applications_by_status"],
        "total_applications": base["total_applications"],
        "total_applications_amount": base["total_applications_amount"],
        "total_vehicles": base["total_vehicles"],
    }
