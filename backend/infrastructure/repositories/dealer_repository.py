"""Dealer-side read/write repository (Phase 7a — G4).

Owns ORM access for dealer self-service surfaces that were previously
handled by the Express ``DealerService`` / ``DealerRepository`` pair:

  * Joining ``users`` + ``companies`` for the dealer profile card.
  * Aggregating per-dealer sales stats over ``leasing_applications``.
  * Listing clients created through the dealer invite funnel (filtered by
  * Partial updates to the dealer user / linked company.

All public functions return plain dicts — ORM models never escape this
module. Writes flush the session but do not commit (router owns commit).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.models.applications import LeasingApplication
from infrastructure.models.companies import Company
from infrastructure.models.users import User
from infrastructure.repositories.application_repository import (
    dealer_child_ownership_clause,
)
from infrastructure.repositories.company_address_guard import (
    ensure_company_addresses_are_not_blank,
)
from infrastructure.repository_timing import timed_repository

# ---------------------------------------------------------------------------
# Whitelists — limit what the profile-update flow can touch.
# Dealer cabinet intentionally excludes role / phone / is_active / company_id;
# those are managed via auth and admin surfaces.
# ---------------------------------------------------------------------------

_USER_UPDATE_FIELDS: frozenset[str] = frozenset(
    {
        "name",
        "email",
    }
)

_COMPANY_UPDATE_FIELDS: frozenset[str] = frozenset(
    {
        "name",
        "inn",
        "kpp",
        "legal_address",
        "actual_address",
        "phone",
        "email",
        "website",
    }
)


@timed_repository
async def get_dealer_user(
    session: AsyncSession, user_id: UUID
) -> dict[str, Any] | None:
    """Return a dict view of the dealer user joined with their company."""
    stmt = (
        sa.select(
            User.id,
            User.phone,
            User.email,
            User.name,
            User.role,
            User.company_id,
            User.is_active,
            User.last_login,
            User.created_at,
            User.updated_at,
            Company.id.label("c_id"),
            Company.name.label("c_name"),
            Company.inn.label("c_inn"),
            Company.kpp.label("c_kpp"),
            Company.ogrn.label("c_ogrn"),
            Company.legal_address.label("c_legal_address"),
            Company.actual_address.label("c_actual_address"),
            Company.phone.label("c_phone"),
            Company.email.label("c_email"),
            Company.website.label("c_website"),
            Company.company_type.label("c_type"),
        )
        .select_from(User)
        .join(Company, Company.id == User.company_id, isouter=True)
        .where(User.id == user_id)
    )
    result = await session.execute(stmt)
    row = result.mappings().first()
    if row is None:
        return None
    user = {
        "id": row["id"],
        "phone": row["phone"],
        "email": row["email"],
        "name": row["name"],
        "role": row["role"],
        "company_id": row["company_id"],
        "is_active": row["is_active"],
        "last_login": row["last_login"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }
    if row["c_id"]:
        company = {
            "id": row["c_id"],
            "name": row["c_name"],
            "inn": row["c_inn"],
            "kpp": row["c_kpp"],
            "ogrn": row["c_ogrn"],
            "legal_address": row["c_legal_address"],
            "actual_address": row["c_actual_address"],
            "phone": row["c_phone"],
            "email": row["c_email"],
            "website": row["c_website"],
            "company_type": row["c_type"],
        }
    else:
        company = None
    return {"user": user, "company": company}


@timed_repository
async def dealer_sales_stats(session: AsyncSession, dealer_id: UUID) -> dict[str, Any]:
    """Aggregate applications-based sales stats for a dealer."""
    approved_statuses = ("active", "issued")
    total_clients_expr = sa.func.count(sa.distinct(LeasingApplication.name))
    total_sales_expr = sa.func.count(
        sa.case(
            (
                LeasingApplication.status.in_(approved_statuses),
                LeasingApplication.id,
            ),
            else_=None,
        )
    )
    total_revenue_expr = sa.func.coalesce(
        sa.func.sum(
            sa.case(
                (
                    LeasingApplication.status.in_(approved_statuses),
                    LeasingApplication.total_amount,
                ),
                else_=0,
            )
        ),
        0,
    )
    stmt = sa.select(
        total_clients_expr.label("total_clients"),
        total_sales_expr.label("total_sales"),
        total_revenue_expr.label("total_revenue"),
        sa.func.count(LeasingApplication.id).label("total_applications"),
    )
    stmt = stmt.where(
        (LeasingApplication.company_id == dealer_id)
        | (LeasingApplication.dealer_company_id == dealer_id)
        | dealer_child_ownership_clause(LeasingApplication.id, dealer_id)
    )
    result = await session.execute(stmt)
    row = result.mappings().one_or_none()
    if row is None:
        return {
            "total_clients": 0,
            "total_sales": 0,
            "total_revenue": 0,
            "total_applications": 0,
            "conversion_rate": 0.0,
        }
    total_applications = int(row["total_applications"] or 0)
    total_sales = int(row["total_sales"] or 0)
    conversion_rate = (
        round(total_sales / total_applications * 100.0, 2)
        if total_applications > 0
        else 0.0
    )
    return {
        "total_clients": int(row["total_clients"] or 0),
        "total_sales": total_sales,
        "total_revenue": float(row["total_revenue"] or 0),
        "total_applications": total_applications,
        "conversion_rate": conversion_rate,
    }


@timed_repository
async def list_dealer_clients(
    session: AsyncSession,
    dealer_id: UUID,
    *,
    search: str | None = None,
    is_active: bool | None = None,
    page: int = 1,
    limit: int = 20,
) -> tuple[list[dict[str, Any]], int]:
    """List unique clients linked to leasing applications created by this dealer.

    Derivation mirrors Express's ``DealerRepository.getClients``: clients
    are users appearing as ``email`` on any application created by the
    dealer (or as the questionnaire's user; here we use ``email`` because
    ``LeasingApplication`` doesn't carry a client user FK directly).
    """
    conditions: list[Any] = [
        LeasingApplication.email.isnot(None),
        sa.or_(
            LeasingApplication.dealer_company_id == dealer_id,
            sa.and_(
                LeasingApplication.dealer_company_id.is_(None),
                LeasingApplication.company_id == dealer_id,
            ),
            dealer_child_ownership_clause(LeasingApplication.id, dealer_id),
        ),
    ]
    if is_active is not None:
        conditions.append(User.is_active == is_active)
    if search:
        pattern = f"%{search}%"
        conditions.append(
            sa.or_(
                sa.func.coalesce(User.name, "").ilike(pattern),
                sa.func.coalesce(User.email, "").ilike(pattern),
                sa.func.coalesce(User.phone, "").ilike(pattern),
            )
        )

    total_stmt = (
        sa.select(sa.func.count(sa.distinct(User.id)))
        .select_from(LeasingApplication)
        .join(User, User.email == LeasingApplication.email)
        .where(*conditions)
    )
    total = int((await session.execute(total_stmt)).scalar() or 0)

    offset = max(0, (page - 1) * limit)
    rows_stmt = (
        sa.select(
            User.id,
            User.name,
            User.email,
            User.phone,
            User.is_active,
            User.last_login,
            User.created_at,
            sa.func.count(LeasingApplication.id).label("applications_count"),
            sa.func.coalesce(sa.func.sum(LeasingApplication.total_amount), 0).label(
                "total_amount"
            ),
        )
        .select_from(LeasingApplication)
        .join(User, User.email == LeasingApplication.email)
        .where(*conditions)
        .group_by(
            User.id,
            User.name,
            User.email,
            User.phone,
            User.is_active,
            User.last_login,
            User.created_at,
        )
        .order_by(sa.func.coalesce(User.created_at, sa.null()).desc())
        .limit(limit)
        .offset(offset)
    )
    rows = (await session.execute(rows_stmt)).mappings().all()
    items = [
        {
            "id": row["id"],
            "name": row["name"],
            "email": row["email"],
            "phone": row["phone"],
            "is_active": row["is_active"],
            "last_login": row["last_login"],
            "created_at": row["created_at"],
            "applications_count": int(row["applications_count"] or 0),
            "total_amount": float(row["total_amount"] or 0),
        }
        for row in rows
    ]
    return items, total


@timed_repository
async def update_dealer_user(
    session: AsyncSession,
    user_id: UUID,
    data: dict[str, Any],
) -> bool:
    """Partial update of the dealer user row."""
    payload = {k: v for k, v in data.items() if k in _USER_UPDATE_FIELDS}
    if not payload:
        return False
    payload["updated_at"] = datetime.now(UTC)
    result = await session.execute(
        sa.update(User).where(User.id == user_id).values(**payload)
    )
    await session.flush()
    return int(cast("sa.engine.CursorResult", result).rowcount or 0) > 0


@timed_repository
async def update_dealer_company(
    session: AsyncSession,
    company_id: UUID,
    data: dict[str, Any],
) -> bool:
    """Partial update of the dealer company row."""
    payload = {k: v for k, v in data.items() if k in _COMPANY_UPDATE_FIELDS}
    ensure_company_addresses_are_not_blank(payload)
    if not payload:
        return False
    payload["updated_at"] = datetime.now(UTC)
    result = await session.execute(
        sa.update(Company).where(Company.id == company_id).values(**payload)
    )
    await session.flush()
    return int(cast("sa.engine.CursorResult", result).rowcount or 0) > 0
