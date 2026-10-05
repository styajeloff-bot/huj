"""Admin-side users repository — async, dict-only API.

Owns ORM access for the ``users`` table inside the admin scope (list /
create / update / soft-delete). Returns plain dicts — ORM objects never
escape this module.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.models.companies import Company
from infrastructure.models.users import User
from infrastructure.repository_timing import timed_repository


def _user_to_dict(row: User) -> dict[str, Any]:
    return {
        "id": row.id,
        "email": row.email,
        "phone": row.phone,
        "name": row.name,
        "role": row.role,
        "company_id": row.company_id,
        "is_active": row.is_active,
        "email_verified": row.email_verified,
        "last_login": row.last_login,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }

@timed_repository
async def list_users(
    session: AsyncSession,
    *,
    page: int = 1,
    limit: int = 20,
    search: str | None = None,
    role: str | None = None,
    is_active: bool | None = None,
    company_id: UUID | None = None,
    phone: str | None = None,
    sort_by: str | None = None,
    sort_order: str = "asc",
) -> tuple[list[dict[str, Any]], int]:
    """List users with filters + pagination + sorting, joining company display fields."""
    conditions: list[Any] = []
    if search:
        pattern = f"%{search}%"
        conditions.append(
            or_(
                func.coalesce(User.name, "").ilike(pattern),
                func.coalesce(User.email, "").ilike(pattern),

            )
        )
    if role:
        conditions.append(User.role == role)
    if is_active is not None:
        conditions.append(User.is_active == is_active)
    if company_id is not None:
        conditions.append(User.company_id == company_id)
    if phone:
        conditions.append(User.phone.ilike(f"%{phone}%"))

    where_clause = and_(*conditions) if conditions else None

    count_stmt = select(func.count(User.id))
    if where_clause is not None:
        count_stmt = count_stmt.where(where_clause)
    total = int((await session.execute(count_stmt)).scalar() or 0)

    # Build order-by clause
    allowed_sorts: dict[str, Any] = {
        "name": func.coalesce(User.name, ""),
        "phone": func.coalesce(User.phone, ""),
        "role": User.role,
        "is_active": User.is_active,
        "created_at": User.created_at,
        "company_name": func.coalesce(Company.name, ""),
    }
    order_col = allowed_sorts.get(sort_by) if sort_by else None
    if order_col is not None:
        if sort_order.lower() == "desc":
            list_stmt = select(
                User,
                Company.name.label("company_name"),
                Company.inn.label("company_inn"),
                Company.company_type.label("company_type"),
            ).join(Company, Company.id == User.company_id, isouter=True).order_by(
                order_col.desc().nulls_last()
            )
        else:
            list_stmt = select(
                User,
                Company.name.label("company_name"),
                Company.inn.label("company_inn"),
                Company.company_type.label("company_type"),
            ).join(Company, Company.id == User.company_id, isouter=True).order_by(
                order_col.asc().nulls_last()
            )
    else:
        list_stmt = (
            select(
                User,
                Company.name.label("company_name"),
                Company.inn.label("company_inn"),
                Company.company_type.label("company_type"),
            )
            .join(Company, Company.id == User.company_id, isouter=True)
            .order_by(User.created_at.desc().nulls_last())
        )

    if where_clause is not None:
        list_stmt = list_stmt.where(where_clause)
    list_stmt = list_stmt.offset((max(page, 1) - 1) * max(limit, 1)).limit(
        max(limit, 1)
    )

    rows = (await session.execute(list_stmt)).all()
    items: list[dict[str, Any]] = []
    for row in rows:
        user_dict = _user_to_dict(row.User)
        user_dict["company_name"] = row.company_name
        user_dict["company_inn"] = row.company_inn
        user_dict["company_type"] = row.company_type
        items.append(user_dict)
    return items, total

@timed_repository
async def get_by_id(
    session: AsyncSession, user_id: UUID
) -> dict[str, Any] | None:
    row = await session.get(User, user_id)
    return _user_to_dict(row) if row is not None else None

@timed_repository
async def get_by_phone(
    session: AsyncSession, phone: str
) -> dict[str, Any] | None:
    stmt = select(User).where(User.phone == phone)
    result = await session.execute(stmt)
    row = result.scalars().first()
    return _user_to_dict(row) if row is not None else None


@timed_repository
async def email_exists(
    session: AsyncSession,
    email: str,
    *,
    exclude_id: UUID | None = None,
) -> bool:
    stmt = select(User.id).where(func.lower(User.email) == email.lower())
    if exclude_id is not None:
        stmt = stmt.where(User.id != exclude_id)
    result = await session.execute(stmt)
    return result.first() is not None

@timed_repository
async def phone_exists(
    session: AsyncSession,
    phone: str,
    *,
    exclude_id: UUID | None = None,
) -> bool:
    stmt = select(User.id).where(User.phone == phone)
    if exclude_id is not None:
        stmt = stmt.where(User.id != exclude_id)
    result = await session.execute(stmt)
    return result.first() is not None

@timed_repository
async def create_user(
    session: AsyncSession,
    *,
    name: str | None,
    email: str | None,
    phone: str,
    role: str,
    company_id: UUID | None,
    is_active: bool,
    email_verified: bool,
    user_id: UUID | None = None,
) -> UUID:
    row = User(
        name=name,
        email=email,
        phone=phone,
        role=role,
        company_id=company_id,
        is_active=is_active,
        email_verified=email_verified,
    )
    if user_id is not None:
        row.id = user_id
    session.add(row)
    await session.flush()
    return row.id

@timed_repository
async def update_user(
    session: AsyncSession,
    user_id: UUID,
    *,
    fields: dict[str, Any],
) -> bool:
    """Apply a partial update. Only known columns are written."""
    row = await session.get(User, user_id)
    if row is None:
        return False
    allowed = {
        "name",
        "email",
        "phone",
        "role",
        "company_id",
        "is_active",
        "email_verified",
    }
    touched = False
    for key, value in fields.items():
        if key not in allowed:
            continue
        setattr(row, key, value)
        touched = True
    if not touched:
        return False
    cast("Any", row).updated_at = datetime.now(UTC)
    await session.flush()
    return True

@timed_repository
async def deactivate_user(session: AsyncSession, user_id: UUID) -> bool:
    """Soft-delete — flip ``is_active`` to False (idempotent)."""
    row = await session.get(User, user_id)
    if row is None:
        return False
    row.is_active = False
    cast("Any", row).updated_at = datetime.now(UTC)
    await session.flush()
    return True

@timed_repository
async def count_active_by_role(session: AsyncSession) -> dict[str, int]:
    stmt = (
        select(User.role, func.count(User.id))
        .where(User.is_active.is_(True))
        .group_by(User.role)
    )
    rows = (await session.execute(stmt)).all()
    return {str(r[0] or "unknown"): int(r[1] or 0) for r in rows}

@timed_repository
async def count_active_total(session: AsyncSession) -> int:
    stmt = select(func.count(User.id)).where(
        User.is_active.is_(True)
    )
    return int((await session.execute(stmt)).scalar() or 0)

@timed_repository
async def company_exists(session: AsyncSession, company_id: UUID) -> bool:
    stmt = select(Company.id).where(Company.id == company_id)
    return (await session.execute(stmt)).first() is not None

@timed_repository
async def list_active_dealers(
    session: AsyncSession,
) -> list[dict[str, Any]]:
    """All active dealer users with company display fields for admin UI."""
    stmt = (
        select(
            User.id,
            User.name,
            User.email,
            User.phone,
            Company.name.label("company_name"),
            Company.inn.label("company_inn"),
        )
        .join(Company, Company.id == User.company_id, isouter=True)
        .where(
            User.role == "dealer",
            User.is_active.is_(True),
        )
        .order_by(func.coalesce(User.name, "").asc())
    )
    rows = (await session.execute(stmt)).all()
    return [
        {
            "id": row.id,
            "name": row.name,
            "email": row.email,
            "phone": row.phone,
            "company_name": row.company_name,
            "company_inn": row.company_inn,
        }
        for row in rows
    ]
