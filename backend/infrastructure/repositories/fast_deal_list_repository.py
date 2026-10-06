"""Bulk reads behind the lists and the card of fast deals.

Lists need the assignees of a whole page and the card of a split deal needs the
sibling deals of its group: both are single queries here instead of one per row.
Every function returns plain dicts and never commits.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from infrastructure.models.companies import Company
from infrastructure.models.fast_deals import FastDeal, FastDealAssignee, FastDealVehicle
from infrastructure.models.users import User
from infrastructure.repositories.fast_deal_access_repository import Scope, scope_clause
from infrastructure.repository_timing import timed_repository

Record = dict[str, Any]


@timed_repository
async def assignees_by_deal(
    session: AsyncSession, deal_ids: list[UUID]
) -> dict[UUID, list[Record]]:
    """Assignees of several deals with user names; the primary one comes first."""
    if not deal_ids:
        return {}
    rows = await session.execute(
        sa.select(
            FastDealAssignee.fast_deal_id,
            FastDealAssignee.company_id,
            FastDealAssignee.user_id,
            FastDealAssignee.role,
            User.name.label("user_name"),
        )
        .join(User, User.id == FastDealAssignee.user_id)
        .where(FastDealAssignee.fast_deal_id.in_(deal_ids))
        .order_by(
            FastDealAssignee.fast_deal_id,
            FastDealAssignee.company_id,
            FastDealAssignee.role.desc(),
        )
    )
    result: dict[UUID, list[Record]] = {}
    for row in rows.all():
        result.setdefault(row.fast_deal_id, []).append(
            {
                "company_id": row.company_id,
                "user_id": row.user_id,
                "user_name": row.user_name,
                "role": row.role,
            }
        )
    return result


@timed_repository
async def list_group_deals(
    session: AsyncSession, *, group_id: UUID, scope: Scope
) -> list[Record]:
    """Deals of one split group that the actor may see; the original deal comes first."""
    dealer = aliased(Company)
    vehicles = (
        sa.select(sa.func.count())
        .where(
            FastDealVehicle.fast_deal_id == FastDeal.id,
            FastDealVehicle.item_status == "active",
        )
        .correlate(FastDeal)
        .scalar_subquery()
    )
    rows = await session.execute(
        sa.select(
            FastDeal.id,
            FastDeal.display_number,
            FastDeal.status,
            FastDeal.dealer_company_id,
            FastDeal.vehicles_total,
            dealer.name.label("dealer_company_name"),
            dealer.inn.label("dealer_company_inn"),
            vehicles.label("vehicle_count"),
        )
        .outerjoin(dealer, dealer.id == FastDeal.dealer_company_id)
        .where(FastDeal.group_id == group_id, scope_clause(scope))
        .order_by(FastDeal.created_at, FastDeal.id)
    )
    return [
        {
            "id": row.id,
            "display_number": row.display_number,
            "status": row.status,
            "dealer_company_id": row.dealer_company_id,
            "dealer_company_name": row.dealer_company_name,
            "dealer_company_inn": row.dealer_company_inn,
            "vehicles_total": row.vehicles_total,
            "vehicle_count": int(row.vehicle_count or 0),
        }
        for row in rows.all()
    ]
