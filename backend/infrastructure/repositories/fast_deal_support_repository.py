"""Supports of fast deal positions: applied programs and requests to a distributor.

Applied programs live in ``application_applied_supports`` with the fast deal as
their source; compensations for them are created only when the deal is confirmed.
Programs are inserted through ``compensation_repository.create_applied_support``;
this module owns their removal and everything about requests to a distributor.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from domain.entities.leasing_calculator import SUPPORT_TYPE_VEHICLE_DISCOUNT
from infrastructure.models.companies import (
    Company,
    DistributorBrand,
    DistributorDealerLink,
)
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

    Only price-reducing programs (vehicle discount) count, in full; the other applied
    programs merely drive compensations. An approved request counts the part that the
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
            ApplicationAppliedSupport.support_type.in_(sorted(SUPPORT_TYPE_VEHICLE_DISCOUNT)),
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


@timed_repository
async def get_applied_support(session: AsyncSession, applied_id: UUID) -> Record | None:
    row = await session.get(ApplicationAppliedSupport, applied_id)
    return _dict(row) if row is not None else None


@timed_repository
async def delete_applied_support(session: AsyncSession, applied_id: UUID) -> None:
    """Remove one applied program; the caller refuses it once compensations exist."""
    await session.execute(
        sa.delete(ApplicationAppliedSupport).where(ApplicationAppliedSupport.id == applied_id)
    )
    await session.flush()


# ------------------------------------------------------------------------- requests

@timed_repository
async def get_support_request(
    session: AsyncSession, request_id: UUID, *, lock: bool = False
) -> Record | None:
    stmt = sa.select(FastDealSupportRequest).where(FastDealSupportRequest.id == request_id)
    if lock:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    row = await session.scalar(stmt)
    return _dict(row) if row is not None else None


@timed_repository
async def insert_support_request(session: AsyncSession, values: Record) -> Record:
    row = FastDealSupportRequest(**values)
    session.add(row)
    await session.flush()
    return _dict(row)


@timed_repository
async def update_support_request(
    session: AsyncSession, request_id: UUID, values: Record
) -> Record:
    await session.execute(
        sa.update(FastDealSupportRequest)
        .where(FastDealSupportRequest.id == request_id)
        .values(**values, updated_at=sa.func.now())
    )
    request = await get_support_request(session, request_id)
    assert request is not None
    return request


@timed_repository
async def account_approved_requests(session: AsyncSession, vehicle_id: UUID) -> list[Record]:
    """Subtract the whole decided amount of the position's approved requests.

    Returns the requests that changed. A request that is already fully accounted is
    left alone, so repeating the action never lowers the price twice.
    """
    rows = await session.scalars(
        sa.select(FastDealSupportRequest)
        .where(
            FastDealSupportRequest.fast_deal_vehicle_id == vehicle_id,
            FastDealSupportRequest.status == "approved",
            FastDealSupportRequest.decided_amount > FastDealSupportRequest.accounted_amount,
        )
        .order_by(FastDealSupportRequest.created_at, FastDealSupportRequest.id)
        .with_for_update()
    )
    changed: list[Record] = []
    for row in rows.all():
        await session.execute(
            sa.update(FastDealSupportRequest)
            .where(FastDealSupportRequest.id == row.id)
            .values(accounted_amount=row.decided_amount, updated_at=sa.func.now())
        )
        changed.append({"id": row.id, "accounted_amount": row.decided_amount})
    await session.flush()
    return changed


# ---------------------------------------------------------------------- distributors

@timed_repository
async def distributors_by_mark(
    session: AsyncSession, dealer_company_id: UUID, mark_ids: list[UUID]
) -> dict[UUID, UUID]:
    """The dealer's linked distributor for each mark that it actively serves.

    A dealer has at most one distributor, and the request goes to nobody else: a mark
    without an active assignment of that distributor has no entry.
    """
    if not mark_ids:
        return {}
    rows = await session.execute(
        sa.select(DistributorBrand.brand_id, DistributorDealerLink.distributor_company_id)
        .select_from(DistributorDealerLink)
        .join(
            DistributorBrand,
            DistributorBrand.distributor_company_id == DistributorDealerLink.distributor_company_id,
        )
        .join(Company, Company.id == DistributorDealerLink.distributor_company_id)
        .where(
            DistributorDealerLink.dealer_company_id == dealer_company_id,
            DistributorBrand.is_active.is_(True),
            DistributorBrand.brand_id.in_(mark_ids),
            Company.company_type == "distributor",
            Company.is_active.is_not(False),
        )
    )
    return {row[0]: row[1] for row in rows.all()}
