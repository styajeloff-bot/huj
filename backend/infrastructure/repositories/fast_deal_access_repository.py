"""Who may see which fast deals: scoped lists, memberships, assignees, company facts.

The SQL scope here and ``application.fast_deals.access.resolve_party`` express the
same rules. Every filter of a list is applied after this server-side restriction.
"""
from __future__ import annotations

from typing import Any, TypedDict
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from infrastructure.models.companies import Company, DistributorDealerLink
from infrastructure.models.fast_deals import (
    FastDeal,
    FastDealAssignee,
    FastDealLcApplication,
    FastDealSupportRequest,
    FastDealVehicle,
)
from infrastructure.models.users import User, UserCompany
from infrastructure.repository_timing import timed_repository

Record = dict[str, Any]


class Scope(TypedDict):
    role: str
    company_id: UUID | None
    user_id: UUID
    is_company_admin: bool


class Filters(TypedDict, total=False):
    number: str
    client_inn: str
    client_company_id: UUID
    leasing_company_id: UUID
    dealer_company_id: UUID
    source_type: str
    status: str


def _dict(row: Any) -> Record:
    return {column.name: getattr(row, column.name) for column in row.__table__.columns}


def _assignee_exists(user_id: UUID, company_id: UUID) -> sa.ColumnElement[bool]:
    return sa.exists().where(
        FastDealAssignee.fast_deal_id == FastDeal.id,
        FastDealAssignee.user_id == user_id,
        FastDealAssignee.company_id == company_id,
    )


def _own_or_assigned(
    scope: Scope, company_id: UUID
) -> sa.ColumnElement[bool]:
    """Author or assignee; a company administrator sees the whole company."""
    if scope["is_company_admin"]:
        return sa.true()
    return sa.or_(
        FastDeal.created_by == scope["user_id"], _assignee_exists(scope["user_id"], company_id)
    )


def _assigned_or_admin(scope: Scope, company_id: UUID) -> sa.ColumnElement[bool]:
    """Counterparty: administrators until someone is assigned, then the assignees."""
    if scope["is_company_admin"]:
        return sa.true()
    return _assignee_exists(scope["user_id"], company_id)


def scope_clause(scope: Scope) -> sa.ColumnElement[bool]:
    """Deals the actor may see; a draft is visible to its initiator side only."""
    role = scope["role"]
    company_id = scope["company_id"]
    sent = sa.and_(FastDeal.sent_at.is_not(None), FastDeal.status != "draft")
    if role == "carcraft_employee":
        return sent
    if company_id is None:
        return sa.false()
    if role == "dealer":
        return sa.or_(
            sa.and_(
                FastDeal.source_type == "dealer_to_leasing",
                FastDeal.initiator_company_id == company_id,
                _own_or_assigned(scope, company_id),
            ),
            sa.and_(
                FastDeal.source_type == "leasing_to_dealer",
                FastDeal.dealer_company_id == company_id,
                sent,
                _assigned_or_admin(scope, company_id),
            ),
        )
    if role == "leasing_company":
        invited = sa.exists().where(
            FastDealLcApplication.fast_deal_id == FastDeal.id,
            FastDealLcApplication.leasing_company_id == company_id,
            FastDealLcApplication.archived_at.is_(None),
        )
        return sa.or_(
            sa.and_(
                FastDeal.source_type == "leasing_to_dealer",
                FastDeal.initiator_company_id == company_id,
                _own_or_assigned(scope, company_id),
            ),
            sa.and_(
                FastDeal.source_type == "dealer_to_leasing",
                FastDeal.status != "draft",
                invited,
                _assigned_or_admin(scope, company_id),
            ),
        )
    if role == "distributor":
        linked = FastDeal.dealer_company_id.in_(
            sa.select(DistributorDealerLink.dealer_company_id).where(
                DistributorDealerLink.distributor_company_id == company_id
            )
        )
        # A support request addressed to the distributor opens the deal to it even as a
        # draft: the decision needs the position, and a DD draft accounts it at once.
        asked = sa.exists().where(
            FastDealSupportRequest.fast_deal_id == FastDeal.id,
            FastDealSupportRequest.distributor_company_id == company_id,
        )
        return sa.and_(linked, sa.or_(sent, asked))
    return sa.false()


def _filter_clause(filters: Filters) -> list[sa.ColumnElement[bool]]:
    clauses: list[sa.ColumnElement[bool]] = []
    number = (filters.get("number") or "").strip()
    if number:
        escaped = number.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        clauses.append(FastDeal.display_number.ilike(f"%{escaped}%", escape="\\"))
    inn = (filters.get("client_inn") or "").strip()
    if inn:
        escaped = inn.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        clauses.append(
            FastDeal.client_company_id.in_(
                sa.select(Company.id).where(Company.inn.like(f"{escaped}%", escape="\\"))
            )
        )
    if filters.get("client_company_id"):
        clauses.append(FastDeal.client_company_id == filters["client_company_id"])
    if filters.get("dealer_company_id"):
        clauses.append(FastDeal.dealer_company_id == filters["dealer_company_id"])
    if filters.get("leasing_company_id"):
        lc_id = filters["leasing_company_id"]
        clauses.append(
            sa.or_(
                FastDeal.leasing_company_id == lc_id,
                sa.exists().where(
                    FastDealLcApplication.fast_deal_id == FastDeal.id,
                    FastDealLcApplication.leasing_company_id == lc_id,
                    FastDealLcApplication.archived_at.is_(None),
                ),
            )
        )
    if filters.get("source_type"):
        clauses.append(FastDeal.source_type == filters["source_type"])
    if filters.get("status"):
        clauses.append(FastDeal.status == filters["status"])
    return clauses


@timed_repository
async def list_deals(
    session: AsyncSession,
    *,
    scope: Scope,
    filters: Filters | None = None,
    limit: int,
    offset: int = 0,
) -> tuple[list[Record], int]:
    """Visible deals newest first with names for the list; ``total`` counts all matches."""
    client = aliased(Company)
    initiator = aliased(Company)
    dealer = aliased(Company)
    leasing = aliased(Company)
    where = [scope_clause(scope), *_filter_clause(filters or {})]
    invited = (
        sa.select(sa.func.count())
        .where(
            FastDealLcApplication.fast_deal_id == FastDeal.id,
            FastDealLcApplication.archived_at.is_(None),
        )
        .correlate(FastDeal)
        .scalar_subquery()
    )
    vehicles = (
        sa.select(sa.func.count())
        .where(
            FastDealVehicle.fast_deal_id == FastDeal.id, FastDealVehicle.item_status == "active"
        )
        .correlate(FastDeal)
        .scalar_subquery()
    )
    total = await session.scalar(sa.select(sa.func.count()).select_from(FastDeal).where(*where))
    stmt = (
        sa.select(
            FastDeal,
            client.name.label("client_name"),
            client.inn.label("client_inn"),
            initiator.name.label("initiator_company_name"),
            dealer.name.label("dealer_company_name"),
            leasing.name.label("leasing_company_name"),
            invited.label("invited_lc_count"),
            vehicles.label("vehicle_count"),
        )
        .join(client, client.id == FastDeal.client_company_id)
        .join(initiator, initiator.id == FastDeal.initiator_company_id)
        .outerjoin(dealer, dealer.id == FastDeal.dealer_company_id)
        .outerjoin(leasing, leasing.id == FastDeal.leasing_company_id)
        .where(*where)
        .order_by(FastDeal.created_at.desc(), FastDeal.id.desc())
        .limit(limit)
        .offset(offset)
    )
    rows = (await session.execute(stmt)).all()
    items = [
        {
            **_dict(row.FastDeal),
            "client_name": row.client_name,
            "client_inn": row.client_inn,
            "initiator_company_name": row.initiator_company_name,
            "dealer_company_name": row.dealer_company_name,
            "leasing_company_name": row.leasing_company_name,
            "invited_lc_count": int(row.invited_lc_count or 0),
            "vehicle_count": int(row.vehicle_count or 0),
        }
        for row in rows
    ]
    return items, int(total or 0)


@timed_repository
async def filter_options(session: AsyncSession, *, scope: Scope) -> Record:
    """Companies that occur in the actor's visible deals: filter dropdown values."""
    visible = scope_clause(scope)
    result: Record = {"clients": [], "leasing_companies": [], "dealers": []}
    clients = await session.execute(
        sa.select(Company.id, Company.name, Company.inn)
        .where(
            Company.id.in_(sa.select(FastDeal.client_company_id).where(visible)),
        )
        .order_by(Company.name)
    )
    result["clients"] = [
        {"id": row.id, "name": row.name, "inn": row.inn} for row in clients.all()
    ]
    chosen = sa.select(FastDeal.leasing_company_id).where(
        visible, FastDeal.leasing_company_id.is_not(None)
    )
    invited = (
        sa.select(FastDealLcApplication.leasing_company_id)
        .join(FastDeal, FastDeal.id == FastDealLcApplication.fast_deal_id)
        .where(visible, FastDealLcApplication.archived_at.is_(None))
    )
    leasing = await session.execute(
        sa.select(Company.id, Company.name, Company.inn)
        .where(sa.or_(Company.id.in_(chosen), Company.id.in_(invited)))
        .order_by(Company.name)
    )
    result["leasing_companies"] = [
        {"id": row.id, "name": row.name, "inn": row.inn} for row in leasing.all()
    ]
    dealers = await session.execute(
        sa.select(Company.id, Company.name, Company.inn)
        .where(Company.id.in_(sa.select(FastDeal.dealer_company_id).where(visible)))
        .order_by(Company.name)
    )
    result["dealers"] = [
        {"id": row.id, "name": row.name, "inn": row.inn} for row in dealers.all()
    ]
    return result


# ---------------------------------------------------------------------- memberships

@timed_repository
async def get_membership(
    session: AsyncSession, user_id: UUID, company_id: UUID
) -> Record | None:
    """Current membership of the user in the company; ``None`` when there is none.

    A legacy user bound only through ``users.company_id`` is an administrator. A
    leasing-company user linked by ``leasing_company_users`` has no row here; the
    caller's company context already established that link.
    """
    row = (
        await session.execute(
            sa.select(UserCompany.is_active, UserCompany.sub_role).where(
                UserCompany.user_id == user_id, UserCompany.company_id == company_id
            )
        )
    ).one_or_none()
    if row is not None:
        return {"is_active": row.is_active is not False, "sub_role": row.sub_role or "employee"}
    legacy = await session.scalar(
        sa.select(User.id).where(User.id == user_id, User.company_id == company_id)
    )
    if legacy is not None:
        return {"is_active": True, "sub_role": "administrator"}
    return None


@timed_repository
async def company_briefs(session: AsyncSession, company_ids: list[UUID]) -> dict[UUID, Record]:
    if not company_ids:
        return {}
    rows = await session.execute(
        sa.select(
            Company.id, Company.name, Company.inn, Company.kpp, Company.company_type,
            Company.phone, Company.is_active,
        ).where(Company.id.in_(company_ids))
    )
    return {
        row.id: {
            "id": row.id,
            "name": row.name,
            "inn": row.inn,
            "kpp": row.kpp,
            "company_type": row.company_type,
            "phone": row.phone,
            "is_active": row.is_active is not False,
        }
        for row in rows.all()
    }


@timed_repository
async def user_briefs(session: AsyncSession, user_ids: list[UUID]) -> dict[UUID, Record]:
    if not user_ids:
        return {}
    rows = await session.execute(
        sa.select(User.id, User.name, User.email, User.phone).where(User.id.in_(user_ids))
    )
    return {
        row.id: {"id": row.id, "name": row.name, "email": row.email, "phone": row.phone}
        for row in rows.all()
    }


@timed_repository
async def distributor_of_dealer(session: AsyncSession, dealer_company_id: UUID) -> UUID | None:
    return await session.scalar(
        sa.select(DistributorDealerLink.distributor_company_id).where(
            DistributorDealerLink.dealer_company_id == dealer_company_id
        )
    )


@timed_repository
async def distributor_has_request(
    session: AsyncSession, deal_id: UUID, distributor_company_id: UUID
) -> bool:
    """Whether a support request of this deal is addressed to the distributor."""
    return bool(
        await session.scalar(
            sa.select(
                sa.exists().where(
                    FastDealSupportRequest.fast_deal_id == deal_id,
                    FastDealSupportRequest.distributor_company_id == distributor_company_id,
                )
            )
        )
    )


@timed_repository
async def linked_dealer_ids(session: AsyncSession, distributor_company_id: UUID) -> list[UUID]:
    rows = await session.scalars(
        sa.select(DistributorDealerLink.dealer_company_id).where(
            DistributorDealerLink.distributor_company_id == distributor_company_id
        )
    )
    return list(rows.all())


# ------------------------------------------------------------------------- assignees

@timed_repository
async def list_assignees(session: AsyncSession, deal_id: UUID) -> list[Record]:
    rows = await session.execute(
        sa.select(
            FastDealAssignee,
            User.name.label("user_name"),
            User.email.label("user_email"),
            Company.name.label("company_name"),
        )
        .join(User, User.id == FastDealAssignee.user_id)
        .join(Company, Company.id == FastDealAssignee.company_id)
        .where(FastDealAssignee.fast_deal_id == deal_id)
        .order_by(FastDealAssignee.company_id, FastDealAssignee.role.desc())
    )
    return [
        {
            **_dict(item),
            "user_name": name,
            "user_email": email,
            "company_name": company,
        }
        for item, name, email, company in rows.all()
    ]


@timed_repository
async def eligible_employees(session: AsyncSession, company_id: UUID) -> list[Record]:
    """Active members of the company who may be assigned to a deal."""
    rows = await session.execute(
        sa.select(User.id, User.name, User.email, UserCompany.sub_role)
        .join(UserCompany, UserCompany.user_id == User.id)
        .where(
            UserCompany.company_id == company_id,
            UserCompany.is_active.is_not(False),
            User.is_active.is_not(False),
            User.deleted_at.is_(None),
        )
        .order_by(User.name, User.id)
    )
    return [
        {"id": r.id, "name": r.name, "email": r.email, "sub_role": r.sub_role or "employee"}
        for r in rows.all()
    ]


@timed_repository
async def active_member_ids(
    session: AsyncSession, company_id: UUID, user_ids: list[UUID]
) -> set[UUID]:
    """Subset of ``user_ids`` that are active members of the company right now."""
    if not user_ids:
        return set()
    rows = await session.scalars(
        sa.select(User.id)
        .join(UserCompany, UserCompany.user_id == User.id)
        .where(
            User.id.in_(user_ids),
            UserCompany.company_id == company_id,
            UserCompany.is_active.is_not(False),
            User.is_active.is_not(False),
            User.deleted_at.is_(None),
        )
    )
    return set(rows.all())


@timed_repository
async def replace_company_assignees(
    session: AsyncSession,
    *,
    deal_id: UUID,
    company_id: UUID,
    primary_user_id: UUID,
    additional_user_id: UUID | None,
    assigned_by: UUID,
) -> tuple[list[Record], list[Record]]:
    """Set the party's assignees; returns ``(before, after)`` of that company."""
    before = [
        item for item in await list_assignees(session, deal_id) if item["company_id"] == company_id
    ]
    await session.execute(
        sa.delete(FastDealAssignee).where(
            FastDealAssignee.fast_deal_id == deal_id, FastDealAssignee.company_id == company_id
        )
    )
    await session.flush()
    session.add(
        FastDealAssignee(
            fast_deal_id=deal_id, company_id=company_id, user_id=primary_user_id,
            role="primary", assigned_by=assigned_by,
        )
    )
    if additional_user_id is not None:
        session.add(
            FastDealAssignee(
                fast_deal_id=deal_id, company_id=company_id, user_id=additional_user_id,
                role="additional", assigned_by=assigned_by,
            )
        )
    await session.flush()
    after = [
        item for item in await list_assignees(session, deal_id) if item["company_id"] == company_id
    ]
    return before, after


@timed_repository
async def company_administrator_ids(session: AsyncSession, company_id: UUID) -> list[UUID]:
    """Active administrators of a company; recipients when nobody is assigned."""
    rows = await session.scalars(
        sa.select(User.id)
        .join(UserCompany, UserCompany.user_id == User.id)
        .where(
            UserCompany.company_id == company_id,
            UserCompany.sub_role == "administrator",
            UserCompany.is_active.is_not(False),
            User.is_active.is_not(False),
            User.deleted_at.is_(None),
        )
        .order_by(User.id)
    )
    return list(rows.all())
