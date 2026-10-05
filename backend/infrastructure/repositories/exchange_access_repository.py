"""Current membership and object projections shared by HTTP and notifications."""
from typing import Any
from uuid import UUID

from sqlalchemy import and_, false, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.models.companies import (
    Company,
    LeasingCompany,
    LeasingCompanyUser,
)
from infrastructure.models.users import User, UserCompany


async def get_actor_role(session: AsyncSession, user_id: UUID) -> str | None:
    return (await session.execute(select(User.role).where(
        User.id == user_id, User.is_active.is_(True), User.deleted_at.is_(None),
    ))).scalar_one_or_none()


async def get_actor_companies(session: AsyncSession, user_id: UUID, role: str) -> list[dict[str, Any]]:
    user = (await session.execute(select(User).where(
        User.id == user_id, User.is_active.is_(True), User.deleted_at.is_(None), User.role == role,
    ))).scalar_one_or_none()
    if user is None:
        return []
    lc_links = select(LeasingCompany.company_id).join(
        LeasingCompanyUser, LeasingCompanyUser.leasing_company_id == LeasingCompany.id,
    ).where(LeasingCompanyUser.user_id == user_id, LeasingCompany.is_active.is_(True))
    stmt = select(Company.id, UserCompany.user_id, UserCompany.can_view_applications,
                  UserCompany.can_create_applications).outerjoin(UserCompany, and_(
        UserCompany.user_id == user_id, UserCompany.company_id == Company.id,
    )).where(Company.is_active.is_(True), Company.company_type == role, or_(
        UserCompany.user_id.is_not(None), Company.id == user.company_id,
        Company.id.in_(lc_links) if role == "leasing_company" else false(),
    ))
    return [{"id": row.id,
             "can_view_applications": bool(row.can_view_applications) if row.user_id else True,
             "can_create_applications": bool(row.can_create_applications) if row.user_id else True}
            for row in (await session.execute(stmt)).all()]
