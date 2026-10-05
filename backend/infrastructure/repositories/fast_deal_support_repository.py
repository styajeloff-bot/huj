"""Supports of fast deal positions: applied programs and requests to a distributor.

Applied programs live in ``application_applied_supports`` with the fast deal as
their source; compensations for them are created only when the deal is confirmed.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.models.fast_deals import FastDealSupportRequest
from infrastructure.models.support import ApplicationAppliedSupport
from infrastructure.repository_timing import timed_repository

Record = dict[str, Any]
ZERO = Decimal("0.00")


def _dict(row: Any) -> Record:
    return {column.name: getattr(row, column.name) for column in row.__table__.columns}


@timed_repository
async def list_applied_supports(session: AsyncSession, deal_id: UUID) -> list[Record]:
    rows = await session.scalars(
        sa.select(ApplicationAppliedSupport)
        .where(ApplicationAppliedSupport.fast_deal_id == deal_id)
        .order_by(ApplicationAppliedSupport.created_at, ApplicationAppliedSupport.id)
    )
    return [_dict(row) for row in rows.all()]


@timed_repository
async def list_support_requests(session: AsyncSession, deal_id: UUID) -> list[Record]:
    rows = await session.scalars(
        sa.select(FastDealSupportRequest)
        .where(FastDealSupportRequest.fast_deal_id == deal_id)
        .order_by(FastDealSupportRequest.created_at, FastDealSupportRequest.id)
    )
    return [_dict(row) for row in rows.all()]


@timed_repository
async def accounted_support_by_vehicle(
    session: AsyncSession, deal_id: UUID
) -> dict[UUID, Decimal]:
    """Support already subtracted from each position's price.

    Applied programs count in full; an approved request counts the part that the
    dealer has accounted, so a decision never lowers the price by itself.
    """
    totals: dict[UUID, Decimal] = {}
    applied = await session.execute(
        sa.select(
            ApplicationAppliedSupport.fast_deal_vehicle_id,
            sa.func.coalesce(sa.func.sum(ApplicationAppliedSupport.support_amount), 0),
        )
        .where(
            ApplicationAppliedSupport.fast_deal_id == deal_id,
            ApplicationAppliedSupport.fast_deal_vehicle_id.is_not(None),
        )
        .group_by(ApplicationAppliedSupport.fast_deal_vehicle_id)
    )
    for vehicle_id, amount in applied.all():
        totals[vehicle_id] = totals.get(vehicle_id, ZERO) + Decimal(amount)
    requested = await session.execute(
        sa.select(
            FastDealSupportRequest.fast_deal_vehicle_id,
            sa.func.coalesce(sa.func.sum(FastDealSupportRequest.accounted_amount), 0),
        )
        .where(
            FastDealSupportRequest.fast_deal_id == deal_id,
            FastDealSupportRequest.status == "approved",
        )
        .group_by(FastDealSupportRequest.fast_deal_vehicle_id)
    )
    for vehicle_id, amount in requested.all():
        totals[vehicle_id] = totals.get(vehicle_id, ZERO) + Decimal(amount)
    return totals


@timed_repository
async def unaccounted_by_vehicle(session: AsyncSession, deal_id: UUID) -> dict[UUID, Decimal]:
    """Approved request amounts not yet subtracted from the price."""
    rows = await session.execute(
        sa.select(
            FastDealSupportRequest.fast_deal_vehicle_id,
            sa.func.coalesce(
                sa.func.sum(
                    FastDealSupportRequest.decided_amount - FastDealSupportRequest.accounted_amount
                ),
                0,
            ),
        )
        .where(
            FastDealSupportRequest.fast_deal_id == deal_id,
            FastDealSupportRequest.status == "approved",
        )
        .group_by(FastDealSupportRequest.fast_deal_vehicle_id)
    )
    return {vehicle_id: Decimal(amount) for vehicle_id, amount in rows.all() if Decimal(amount) > 0}
