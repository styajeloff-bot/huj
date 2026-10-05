"""Reporting repository — Phase 6 F1 reports domain.

Async, dict-only API. Read-only aggregations over the already-migrated
domains (leasing applications, application vehicles, purchase orders,
payments, users, companies, leasing companies, distributors).

Express schema references (``users.distributor_id``,
``applications.user_id``, ``application_vehicles.price``) do NOT exist
in the current FastAPI ORM (Alembic heads 001..014). We express the
same intent using the real columns:

- Distributor ownership uses the trivial mapping "distributor scope ==
  vehicles whose ``dealer_id`` points at a user whose ``company_id``
  matches ``distributors.company_id``" (see ``distributor_repository``).
- Vehicle value on an application line is ``application_vehicles.total_price``
  (quantity * unit_price) with a fallback to ``unit_price`` when the total
  column is null.
- ``purchase_orders.total_price`` is the source for realised revenue; a
  purchase in status ``purchased`` / ``leasing_active`` counts as closed.

Queries accept optional timezone-aware ``date_from`` / ``date_to`` and a
filter scope (``role``, actor ids, LC id, distributor id). Every aggregate
returns plain dicts / lists of dicts; no ORM objects escape this module.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.models.applications import (
    LeasingApplication,
    LeasingCompanyApplication,
)
from infrastructure.models.companies import (
    Company,
    Distributor,
    LeasingCompany,
)
from infrastructure.models.payments import PurchaseOrder
from infrastructure.models.special_equipment import SpecialEquipmentProduct
from infrastructure.models.users import User
from infrastructure.repositories.application_repository import (
    dealer_child_ownership_clause,
)
from infrastructure.repository_timing import timed_repository

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _apply_date_range(
    stmt: Any,
    column: Any,
    date_from: datetime | None,
    date_to: datetime | None,
) -> Any:
    if date_from is not None:
        stmt = stmt.where(column >= date_from)
    if date_to is not None:
        stmt = stmt.where(column <= date_to)
    return stmt


def _dealer_application_scope(dealer_id: UUID) -> Any:
    return or_(
        LeasingApplication.dealer_company_id == dealer_id,
        and_(
            LeasingApplication.dealer_company_id.is_(None),
            LeasingApplication.company_id == dealer_id,
        ),
        dealer_child_ownership_clause(LeasingApplication.id, dealer_id),
    )

# ---------------------------------------------------------------------------
# Admin dashboard
# ---------------------------------------------------------------------------

@timed_repository
async def admin_overview(
    session: AsyncSession,
    *,
    date_from: datetime | None,
    date_to: datetime | None,
) -> dict[str, Any]:
    """Top-level KPIs: totals per status + dealers + revenue."""
    stmt = select(
        func.count(LeasingApplication.id.distinct()).label("total_applications"),
        func.count(
            case(
                (LeasingApplication.status == "active", LeasingApplication.id),
                else_=None,
            ).distinct()
        ).label("submitted_applications"),
        func.count(
            case(
                (LeasingApplication.status == "active", LeasingApplication.id),
                else_=None,
            ).distinct()
        ).label("approved_applications"),
        func.count(
            case(
                (LeasingApplication.status == "rejected", LeasingApplication.id),
                else_=None,
            ).distinct()
        ).label("rejected_applications"),
        func.count(
            case(
                (LeasingApplication.status == "active", LeasingApplication.id),
                else_=None,
            ).distinct()
        ).label("under_review_applications"),
        func.coalesce(func.sum(LeasingApplication.total_amount), 0).label(
            "total_amount"
        ),
    )
    stmt = _apply_date_range(
        stmt, LeasingApplication.created_at, date_from, date_to
    )
    row = (await session.execute(stmt)).mappings().first()

    # Users + vehicles counters (no date filter on users — it's a headcount).
    users_total = (
        await session.execute(select(func.count(User.id)))
    ).scalar() or 0
    dealers_total = (
        await session.execute(
            select(func.count(User.id)).where(User.role == "dealer")
        )
    ).scalar() or 0

    # Realised revenue — only purchased / leasing_active count.
    revenue_stmt = select(
        func.coalesce(func.sum(PurchaseOrder.total_price), 0)
    ).where(
        PurchaseOrder.status.in_(("purchased", "leasing_active"))
    )
    revenue_stmt = _apply_date_range(
        revenue_stmt, PurchaseOrder.created_at, date_from, date_to
    )
    total_revenue = (await session.execute(revenue_stmt)).scalar() or 0

    approved = int(row["approved_applications"]) if row else 0
    total = int(row["total_applications"]) if row else 0
    approval_rate = round((approved / total) * 100, 2) if total else 0.0

    return {
        "total_applications": int(row["total_applications"]) if row else 0,
        "submitted_applications": int(row["submitted_applications"]) if row else 0,
        "approved_applications": approved,
        "rejected_applications": int(row["rejected_applications"]) if row else 0,
        "under_review_applications": int(
            row["under_review_applications"]
        )
        if row
        else 0,
        "total_amount": row["total_amount"] if row else 0,
        "total_revenue": total_revenue,
        "total_users": int(users_total),
        "total_dealers": int(dealers_total),
        "approval_rate": approval_rate,
    }

@timed_repository
async def admin_status_distribution(
    session: AsyncSession,
    *,
    date_from: datetime | None,
    date_to: datetime | None,
) -> list[dict[str, Any]]:
    stmt = (
        select(
            LeasingApplication.status,
            func.count(LeasingApplication.id).label("count"),
        )
        .group_by(LeasingApplication.status)
        .order_by(func.count(LeasingApplication.id).desc())
    )
    stmt = _apply_date_range(
        stmt, LeasingApplication.created_at, date_from, date_to
    )
    rows = (await session.execute(stmt)).all()
    total = sum(int(r[1] or 0) for r in rows) or 0
    result: list[dict[str, Any]] = []
    for status, count in rows:
        c = int(count or 0)
        percentage = round((c / total) * 100, 2) if total else 0.0
        result.append(
            {
                "status": str(status or "unknown"),
                "count": c,
                "percentage": percentage,
            }
        )
    return result

@timed_repository
async def admin_timeline(
    session: AsyncSession,
    *,
    date_from: datetime | None,
    date_to: datetime | None,
    granularity: str = "day",
) -> list[dict[str, Any]]:
    """Return a time series: period → count + approved_count + total_amount."""
    if granularity not in {"day", "week", "month"}:
        granularity = "day"
    period = func.date_trunc(granularity, LeasingApplication.created_at)
    stmt = (
        select(
            period.label("period"),
            func.count(LeasingApplication.id).label("count"),
            func.count(
                case(
                    (
                        LeasingApplication.status == "active",
                        LeasingApplication.id,
                    ),
                    else_=None,
                )
            ).label("approved_count"),
            func.coalesce(func.sum(LeasingApplication.total_amount), 0).label(
                "total_amount"
            ),
        )
        .group_by(period)
        .order_by(period.asc())
    )
    stmt = _apply_date_range(
        stmt, LeasingApplication.created_at, date_from, date_to
    )
    rows = (await session.execute(stmt)).mappings().all()
    return [
        {
            "period": r["period"],
            "count": int(r["count"] or 0),
            "approved_count": int(r["approved_count"] or 0),
            "total_amount": r["total_amount"],
        }
        for r in rows
    ]

@timed_repository
async def top_dealers(
    session: AsyncSession,
    *,
    date_from: datetime | None,
    date_to: datetime | None,
    limit: int = 10,
) -> list[dict[str, Any]]:
    stmt = (
        select(
            User.id.label("dealer_id"),
            User.name.label("dealer_name"),
            User.email.label("dealer_email"),
            func.count(LeasingApplication.id.distinct()).label(
                "applications_count"
            ),
            func.count(
                case(
                    (
                        LeasingApplication.status == "active",
                        LeasingApplication.id,
                    ),
                    else_=None,
                ).distinct()
            ).label("approved_count"),
            func.coalesce(
                func.sum(LeasingApplication.total_amount), 0
            ).label("total_amount"),
        )
        .select_from(User)
        .join(
            LeasingApplication,
            isouter=True,
        )
        .where(User.role == "dealer")
        .group_by(User.id, User.name, User.email)
        .order_by(func.count(LeasingApplication.id.distinct()).desc())
        .limit(limit)
    )
    stmt = _apply_date_range(
        stmt, LeasingApplication.created_at, date_from, date_to
    )
    rows = (await session.execute(stmt)).mappings().all()
    return [
        {
            "dealer_id": r["dealer_id"],
            "dealer_name": r["dealer_name"] or "",
            "dealer_email": r["dealer_email"] or "",
            "applications_count": int(r["applications_count"] or 0),
            "approved_count": int(r["approved_count"] or 0),
            "total_amount": r["total_amount"],
            "approval_rate": (
                round(
                    (int(r["approved_count"] or 0) / int(r["applications_count"] or 1))
                    * 100,
                    2,
                )
                if int(r["applications_count"] or 0)
                else 0.0
            ),
        }
        for r in rows
    ]

@timed_repository
async def top_leasing_companies(
    session: AsyncSession,
    *,
    date_from: datetime | None,
    date_to: datetime | None,
    limit: int = 10,
) -> list[dict[str, Any]]:
    stmt = (
        select(
            LeasingCompany.id.label("leasing_company_id"),
            Company.name.label("company_name"),
            func.count(LeasingCompanyApplication.id.distinct()).label(
                "applications_count"
            ),
            func.count(
                case(
                    (
                        LeasingCompanyApplication.status.in_(
                            ("approved_final", "approved_final_another_cond")
                        ),
                        LeasingCompanyApplication.id,
                    ),
                    else_=None,
                ).distinct()
            ).label("approved_count"),
            func.count(
                case(
                    (
                        LeasingCompanyApplication.status.in_(
                            ("rejected_prescoring", "rejected_approved", "closed")
                        ),
                        LeasingCompanyApplication.id,
                    ),
                    else_=None,
                ).distinct()
            ).label("rejected_count"),
        )
        .select_from(LeasingCompany)
        .join(
            Company,
            Company.id == LeasingCompany.company_id,
            isouter=True,
        )
        .join(
            LeasingCompanyApplication,
            LeasingCompanyApplication.leasing_company_id == LeasingCompany.id,
            isouter=True,
        )
        .where(LeasingCompany.is_active.is_(True))
        .group_by(LeasingCompany.id, Company.name)
        .order_by(func.count(LeasingCompanyApplication.id.distinct()).desc())
        .limit(limit)
    )
    stmt = _apply_date_range(
        stmt, LeasingCompanyApplication.created_at, date_from, date_to
    )
    rows = (await session.execute(stmt)).mappings().all()
    return [
        {
            "leasing_company_id": r["leasing_company_id"],
            "company_name": r["company_name"] or "",
            "applications_count": int(r["applications_count"] or 0),
            "approved_count": int(r["approved_count"] or 0),
            "rejected_count": int(r["rejected_count"] or 0),
            "approval_rate": (
                round(
                    (int(r["approved_count"] or 0) / int(r["applications_count"] or 1))
                    * 100,
                    2,
                )
                if int(r["applications_count"] or 0)
                else 0.0
            ),
        }
        for r in rows
    ]

# ---------------------------------------------------------------------------
# Dealer report
# ---------------------------------------------------------------------------

@timed_repository
async def dealer_overview(
    session: AsyncSession,
    *,
    dealer_id: UUID,
    date_from: datetime | None,
    date_to: datetime | None,
) -> dict[str, Any]:
    stmt = select(
        func.count(LeasingApplication.id.distinct()).label("total_applications"),
        func.count(
            case(
                (LeasingApplication.status == "active", LeasingApplication.id),
                else_=None,
            ).distinct()
        ).label("approved_applications"),
        func.count(
            case(
                (LeasingApplication.status == "rejected", LeasingApplication.id),
                else_=None,
            ).distinct()
        ).label("rejected_applications"),
        func.coalesce(func.sum(LeasingApplication.total_amount), 0).label(
            "total_amount"
        ),
    ).where(_dealer_application_scope(dealer_id))
    stmt = _apply_date_range(
        stmt, LeasingApplication.created_at, date_from, date_to
    )
    row = (await session.execute(stmt)).mappings().first()

    # Products under this dealer (current inventory — no date filter).
    vehicles_total = (
        await session.execute(
            select(func.count(SpecialEquipmentProduct.id)).where(SpecialEquipmentProduct.seller_company_id == dealer_id)
        )
    ).scalar() or 0

    total = int(row["total_applications"]) if row else 0
    approved = int(row["approved_applications"]) if row else 0
    approval_rate = round((approved / total) * 100, 2) if total else 0.0
    return {
        "total_applications": total,
        "approved_applications": approved,
        "rejected_applications": int(row["rejected_applications"])
        if row
        else 0,
        "total_amount": row["total_amount"] if row else 0,
        "total_vehicles": int(vehicles_total),
        "approval_rate": approval_rate,
    }

@timed_repository
async def dealer_applications(
    session: AsyncSession,
    *,
    dealer_id: UUID,
    date_from: datetime | None,
    date_to: datetime | None,
) -> list[dict[str, Any]]:
    stmt = (
        select(
            LeasingApplication.id,
            LeasingApplication.status,
            LeasingApplication.total_amount,
            LeasingApplication.created_at,
            LeasingApplication.updated_at,
            LeasingApplication.company_id,
            LeasingApplication.name,
            LeasingApplication.email,
        )
        .where(_dealer_application_scope(dealer_id))
        .order_by(LeasingApplication.created_at.desc())
    )
    stmt = _apply_date_range(
        stmt, LeasingApplication.created_at, date_from, date_to
    )
    rows = (await session.execute(stmt)).mappings().all()
    return [dict(r) for r in rows]

@timed_repository
async def dealer_status_distribution(
    session: AsyncSession,
    *,
    dealer_id: UUID,
    date_from: datetime | None,
    date_to: datetime | None,
) -> list[dict[str, Any]]:
    stmt = (
        select(
            LeasingApplication.status,
            func.count(LeasingApplication.id).label("count"),
        )
        .where(_dealer_application_scope(dealer_id))
        .group_by(LeasingApplication.status)
    )
    stmt = _apply_date_range(
        stmt, LeasingApplication.created_at, date_from, date_to
    )
    rows = (await session.execute(stmt)).all()
    total = sum(int(r[1] or 0) for r in rows) or 0
    return [
        {
            "status": str(status or "unknown"),
            "count": int(count or 0),
            "percentage": round((int(count or 0) / total) * 100, 2)
            if total
            else 0.0,
        }
        for status, count in rows
    ]

@timed_repository
async def dealer_timeline(
    session: AsyncSession,
    *,
    dealer_id: UUID,
    date_from: datetime | None,
    date_to: datetime | None,
    granularity: str = "day",
) -> list[dict[str, Any]]:
    if granularity not in {"day", "week", "month"}:
        granularity = "day"
    period = func.date_trunc(granularity, LeasingApplication.created_at)
    stmt = (
        select(
            period.label("period"),
            func.count(LeasingApplication.id).label("count"),
            func.count(
                case(
                    (
                        LeasingApplication.status == "active",
                        LeasingApplication.id,
                    ),
                    else_=None,
                )
            ).label("approved_count"),
            func.coalesce(func.sum(LeasingApplication.total_amount), 0).label(
                "total_amount"
            ),
        )
        .where(_dealer_application_scope(dealer_id))
        .group_by(period)
        .order_by(period.asc())
    )
    stmt = _apply_date_range(
        stmt, LeasingApplication.created_at, date_from, date_to
    )
    rows = (await session.execute(stmt)).mappings().all()
    return [
        {
            "period": r["period"],
            "count": int(r["count"] or 0),
            "approved_count": int(r["approved_count"] or 0),
            "total_amount": r["total_amount"],
        }
        for r in rows
    ]

# ---------------------------------------------------------------------------
# Leasing company report
# ---------------------------------------------------------------------------

@timed_repository
async def leasing_company_overview(
    session: AsyncSession,
    *,
    leasing_company_id: UUID,
    date_from: datetime | None,
    date_to: datetime | None,
) -> dict[str, Any]:
    stmt = select(
        func.count(LeasingApplication.id.distinct()).label("total_applications"),
        func.count(
            case(
                (LeasingApplication.status == "active", LeasingApplication.id),
                else_=None,
            ).distinct()
        ).label("approved_applications"),
        func.count(
            case(
                (LeasingApplication.status == "rejected", LeasingApplication.id),
                else_=None,
            ).distinct()
        ).label("rejected_applications"),
        func.count(
            case(
                (
                    LeasingApplication.status == "active",
                    LeasingApplication.id,
                ),
                else_=None,
            ).distinct()
        ).label("under_review_applications"),
        func.coalesce(func.sum(LeasingApplication.total_amount), 0).label(
            "total_amount"
        ),
    ).where(
        LeasingApplication.selected_leasing_companies.contains([leasing_company_id])
    )
    stmt = _apply_date_range(
        stmt, LeasingApplication.created_at, date_from, date_to
    )
    row = (await session.execute(stmt)).mappings().first()

    total = int(row["total_applications"]) if row else 0
    approved = int(row["approved_applications"]) if row else 0
    approval_rate = round((approved / total) * 100, 2) if total else 0.0
    return {
        "total_applications": total,
        "approved_applications": approved,
        "rejected_applications": int(row["rejected_applications"])
        if row
        else 0,
        "under_review_applications": int(row["under_review_applications"])
        if row
        else 0,
        "total_amount": row["total_amount"] if row else 0,
        "approval_rate": approval_rate,
    }

@timed_repository
async def leasing_company_applications(
    session: AsyncSession,
    *,
    leasing_company_id: UUID,
    date_from: datetime | None,
    date_to: datetime | None,
) -> list[dict[str, Any]]:
    stmt = (
        select(
            LeasingApplication.id,
            LeasingApplication.status,
            LeasingApplication.total_amount,
            LeasingApplication.created_at,
            LeasingApplication.updated_at,
            LeasingApplication.company_id,
            LeasingApplication.name,
            LeasingApplication.email,
        )
        .where(
            LeasingApplication.selected_leasing_companies.contains(
                [leasing_company_id]
            )
        )
        .order_by(LeasingApplication.created_at.desc())
    )
    stmt = _apply_date_range(
        stmt, LeasingApplication.created_at, date_from, date_to
    )
    rows = (await session.execute(stmt)).mappings().all()
    return [dict(r) for r in rows]

@timed_repository
async def leasing_company_status_distribution(
    session: AsyncSession,
    *,
    leasing_company_id: UUID,
    date_from: datetime | None,
    date_to: datetime | None,
) -> list[dict[str, Any]]:
    stmt = (
        select(
            LeasingApplication.status,
            func.count(LeasingApplication.id).label("count"),
        )
        .where(
            LeasingApplication.selected_leasing_companies.contains(
                [leasing_company_id]
            )
        )
        .group_by(LeasingApplication.status)
    )
    stmt = _apply_date_range(
        stmt, LeasingApplication.created_at, date_from, date_to
    )
    rows = (await session.execute(stmt)).all()
    total = sum(int(r[1] or 0) for r in rows) or 0
    return [
        {
            "status": str(status or "unknown"),
            "count": int(count or 0),
            "percentage": round((int(count or 0) / total) * 100, 2)
            if total
            else 0.0,
        }
        for status, count in rows
    ]

@timed_repository
async def leasing_company_timeline(
    session: AsyncSession,
    *,
    leasing_company_id: UUID,
    date_from: datetime | None,
    date_to: datetime | None,
    granularity: str = "day",
) -> list[dict[str, Any]]:
    if granularity not in {"day", "week", "month"}:
        granularity = "day"
    period = func.date_trunc(granularity, LeasingApplication.created_at)
    stmt = (
        select(
            period.label("period"),
            func.count(LeasingApplication.id).label("count"),
            func.count(
                case(
                    (
                        LeasingApplication.status == "active",
                        LeasingApplication.id,
                    ),
                    else_=None,
                )
            ).label("approved_count"),
            func.coalesce(func.sum(LeasingApplication.total_amount), 0).label(
                "total_amount"
            ),
        )
        .where(
            LeasingApplication.selected_leasing_companies.contains(
                [leasing_company_id]
            )
        )
        .group_by(period)
        .order_by(period.asc())
    )
    stmt = _apply_date_range(
        stmt, LeasingApplication.created_at, date_from, date_to
    )
    rows = (await session.execute(stmt)).mappings().all()
    return [
        {
            "period": r["period"],
            "count": int(r["count"] or 0),
            "approved_count": int(r["approved_count"] or 0),
            "total_amount": r["total_amount"],
        }
        for r in rows
    ]

# ---------------------------------------------------------------------------
# Distributor report
# ---------------------------------------------------------------------------

@timed_repository
async def distributor_overview(
    session: AsyncSession,
    *,
    distributor_company_id: UUID,
    date_from: datetime | None,
    date_to: datetime | None,
) -> dict[str, Any]:
    """Overview of vehicles + apps attached to a distributor's dealer users.

    We reuse the ``users.company_id == distributors.company_id`` trivial
    mapping introduced by Phase 1 B3 / :func:`get_distributor_for_user`.
    """
    # Products owned by this distributor.
    vehicles_total_stmt = (
        select(func.count(SpecialEquipmentProduct.id.distinct()))
        .where(SpecialEquipmentProduct.seller_company_id == distributor_company_id)
    )
    vehicles_total = (await session.execute(vehicles_total_stmt)).scalar() or 0

    # Applications raised by those dealers.
    apps_stmt = (
        select(
            func.count(LeasingApplication.id.distinct()).label("total_applications"),
            func.count(
                case(
                    (
                        LeasingApplication.status == "active",
                        LeasingApplication.id,
                    ),
                    else_=None,
                ).distinct()
            ).label("approved_applications"),
            func.count(
                case(
                    (
                        LeasingApplication.status == "rejected",
                        LeasingApplication.id,
                    ),
                    else_=None,
                ).distinct()
            ).label("rejected_applications"),
            func.coalesce(func.sum(LeasingApplication.total_amount), 0).label(
                "total_amount"
            ),
            func.count(
            ).label("active_dealers"),
        )
        .select_from(LeasingApplication)
        .join(
            User,
            isouter=True,
        )
        .where(User.company_id == distributor_company_id)
    )
    apps_stmt = _apply_date_range(
        apps_stmt, LeasingApplication.created_at, date_from, date_to
    )
    apps_row = (await session.execute(apps_stmt)).mappings().first()

    total = int(apps_row["total_applications"]) if apps_row else 0
    approved = int(apps_row["approved_applications"]) if apps_row else 0
    approval_rate = round((approved / total) * 100, 2) if total else 0.0
    return {
        "total_applications": total,
        "approved_applications": approved,
        "rejected_applications": int(apps_row["rejected_applications"])
        if apps_row
        else 0,
        "total_amount": apps_row["total_amount"] if apps_row else 0,
        "total_vehicles": int(vehicles_total),
        "active_dealers": int(apps_row["active_dealers"]) if apps_row else 0,
        "approval_rate": approval_rate,
    }

@timed_repository
async def distributor_applications(
    session: AsyncSession,
    *,
    distributor_company_id: UUID,
    date_from: datetime | None,
    date_to: datetime | None,
) -> list[dict[str, Any]]:
    stmt = (
        select(
            LeasingApplication.id,
            LeasingApplication.status,
            LeasingApplication.total_amount,
            LeasingApplication.created_at,
            LeasingApplication.updated_at,
            LeasingApplication.company_id,
            LeasingApplication.name,
            LeasingApplication.email,
        )
        .select_from(LeasingApplication)
        .join(
            User,
            isouter=True,
        )
        .where(User.company_id == distributor_company_id)
        .order_by(LeasingApplication.created_at.desc())
    )
    stmt = _apply_date_range(
        stmt, LeasingApplication.created_at, date_from, date_to
    )
    rows = (await session.execute(stmt)).mappings().all()
    return [dict(r) for r in rows]

@timed_repository
async def distributor_timeline(
    session: AsyncSession,
    *,
    distributor_company_id: UUID,
    date_from: datetime | None,
    date_to: datetime | None,
    granularity: str = "day",
) -> list[dict[str, Any]]:
    if granularity not in {"day", "week", "month"}:
        granularity = "day"
    period = func.date_trunc(granularity, LeasingApplication.created_at)
    stmt = (
        select(
            period.label("period"),
            func.count(LeasingApplication.id).label("count"),
            func.count(
                case(
                    (
                        LeasingApplication.status == "active",
                        LeasingApplication.id,
                    ),
                    else_=None,
                )
            ).label("approved_count"),
            func.coalesce(func.sum(LeasingApplication.total_amount), 0).label(
                "total_amount"
            ),
        )
        .select_from(LeasingApplication)
        .join(
            User,
            isouter=True,
        )
        .where(User.company_id == distributor_company_id)
        .group_by(period)
        .order_by(period.asc())
    )
    stmt = _apply_date_range(
        stmt, LeasingApplication.created_at, date_from, date_to
    )
    rows = (await session.execute(stmt)).mappings().all()
    return [
        {
            "period": r["period"],
            "count": int(r["count"] or 0),
            "approved_count": int(r["approved_count"] or 0),
            "total_amount": r["total_amount"],
        }
        for r in rows
    ]

# ---------------------------------------------------------------------------
# Client (own applications)
# ---------------------------------------------------------------------------

@timed_repository
async def client_overview(
    session: AsyncSession,
    *,
    company_id: UUID,
    date_from: datetime | None,
    date_to: datetime | None,
) -> dict[str, Any]:
    stmt = select(
        func.count(LeasingApplication.id.distinct()).label("total_applications"),
        func.count(
            case(
                (LeasingApplication.status == "active", LeasingApplication.id),
                else_=None,
            ).distinct()
        ).label("approved_applications"),
        func.count(
            case(
                (LeasingApplication.status == "rejected", LeasingApplication.id),
                else_=None,
            ).distinct()
        ).label("rejected_applications"),
        func.coalesce(func.sum(LeasingApplication.total_amount), 0).label(
            "total_amount"
        ),
    ).where(LeasingApplication.company_id == company_id)
    stmt = _apply_date_range(
        stmt, LeasingApplication.created_at, date_from, date_to
    )
    row = (await session.execute(stmt)).mappings().first()
    total = int(row["total_applications"]) if row else 0
    approved = int(row["approved_applications"]) if row else 0
    approval_rate = round((approved / total) * 100, 2) if total else 0.0
    return {
        "total_applications": total,
        "approved_applications": approved,
        "rejected_applications": int(row["rejected_applications"])
        if row
        else 0,
        "total_amount": row["total_amount"] if row else 0,
        "approval_rate": approval_rate,
    }

# ---------------------------------------------------------------------------
# Distributor identity lookup
# ---------------------------------------------------------------------------

@timed_repository
async def get_distributor_company_id_for_user(
    session: AsyncSession, user_id: UUID
) -> UUID | None:
    """Resolve the ``distributors.company_id`` for the given user.

    Mirrors :func:`infrastructure.repositories.distributor_repository.
    get_distributor_for_user` but returns only the company_id (enough to
    scope reporting queries) to keep the repository boundary narrow.
    """
    stmt = (
        select(Distributor.company_id)
        .join(User, User.company_id == Distributor.company_id)
        .where(User.id == user_id)
    )
    result = await session.execute(stmt)
    row = result.first()
    if row is None:
        return None
    company_id: UUID | None = row[0]
    return company_id

__all__ = [
    "admin_overview",
    "admin_status_distribution",
    "admin_timeline",
    "client_overview",
    "dealer_applications",
    "dealer_overview",
    "dealer_status_distribution",
    "dealer_timeline",
    "distributor_applications",
    "distributor_overview",
    "distributor_timeline",
    "get_distributor_company_id_for_user",
    "leasing_company_applications",
    "leasing_company_overview",
    "leasing_company_status_distribution",
    "leasing_company_timeline",
    "top_dealers",
    "top_leasing_companies",
]
