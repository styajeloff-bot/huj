"""Admin platform stats repository — aggregated counts across domains.

Returns simple dict aggregates for the top-level admin dashboard. Does
not mutate anything — pure read-side.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.models.applications import LeasingApplication
from infrastructure.models.special_equipment import SpecialEquipmentProduct
from infrastructure.repository_timing import timed_repository


@timed_repository
async def count_total_vehicles(session: AsyncSession) -> int:
    stmt = select(func.count(SpecialEquipmentProduct.id))
    return int((await session.execute(stmt)).scalar() or 0)

@timed_repository
async def count_applications_by_status(
    session: AsyncSession,
) -> dict[str, int]:
    stmt = (
        select(LeasingApplication.status, func.count(LeasingApplication.id))
        .group_by(LeasingApplication.status)
    )
    rows = (await session.execute(stmt)).all()
    return {str(r[0] or "unknown"): int(r[1] or 0) for r in rows}

@timed_repository
async def count_applications_total(session: AsyncSession) -> int:
    stmt = select(func.count(LeasingApplication.id))
    return int((await session.execute(stmt)).scalar() or 0)

@timed_repository
async def sum_applications_total_amount(session: AsyncSession) -> Decimal:
    stmt = select(func.coalesce(func.sum(LeasingApplication.total_amount), 0))
    value = (await session.execute(stmt)).scalar() or 0
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))

@timed_repository
async def aggregate_stats(session: AsyncSession) -> dict[str, Any]:
    """Combine all admin-dashboard KPIs into a single dict."""
    applications_by_status = await count_applications_by_status(session)
    return {
        "applications_by_status": applications_by_status,
        "total_applications": await count_applications_total(session),
        "total_vehicles": await count_total_vehicles(session),
        "total_applications_amount": await sum_applications_total_amount(
            session
        ),
    }
