"""Leasing-company-application repository — Phase 4 D3.

Async, dict-only. Owns writes to ``leasing_company_applications`` and read
projections of the ``leasing_companies`` reference data needed by the LC
workflow. Reads from ``leasing_applications`` (owned by Phase 3) are kept
to the tiny projection ``get_application_projection``; writes to
``leasing_applications.status`` are mediated via Phase 3's own repo — here
we only expose them through small, scoped helpers.

Returns plain dicts / lists of dicts. ORM objects never cross this
boundary.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from domain.entities.leasing_company_application import (
    LCA_STATUS_APPROVED_SCORING,
    LCA_STATUS_APPROVED_SCORING_ANOTHER_COND,
)
from infrastructure.models.applications import (
    ApplicationVehicle,
    LeasingApplication,
    LeasingApplicationComment,
    LeasingCompanyApplication,
)
from infrastructure.models.companies import (
    Company,
    LeasingCompany,
    LeasingCompanyUser,
)
from infrastructure.models.users import User, UserCompany
from infrastructure.repositories import documents_repository as docs_repo
from infrastructure.repositories import status_history_repository as history_repo
from infrastructure.repositories.application_repository import (
    dealer_child_ownership_clause,
)
from infrastructure.repositories.application_source_filters import (
    application_source_filters,
)
from infrastructure.repository_timing import timed_repository


def _lca_to_dict(row: LeasingCompanyApplication) -> dict[str, Any]:
    return {
        "id": row.id,
        "application_id": row.application_id,
        "leasing_company_id": row.leasing_company_id,
        "status": row.status,
        "review_notes": row.review_notes,
        "decision_comment": row.decision_comment,
        "response_pdf_s3_key": row.response_pdf_s3_key,
        "response_pdf_file_name": row.response_pdf_file_name,
        "response_pdf_size": row.response_pdf_size,
        "response_pdf_uploaded_at": row.response_pdf_uploaded_at,
        "submitted_at": row.submitted_at,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }

# ---------------------------------------------------------------------------
# Public LC directory
# ---------------------------------------------------------------------------

@timed_repository
async def list_active_leasing_companies(
    session: AsyncSession,
) -> list[dict[str, Any]]:
    """Return active LCs joined with their ``companies`` display name."""
    stmt = (
        select(
            LeasingCompany.id,
            LeasingCompany.company_id,
            LeasingCompany.average_down_payment_percent,
            LeasingCompany.average_lease_term_months,
            LeasingCompany.average_markup_percent,
            LeasingCompany.min_down_payment_percent,
            LeasingCompany.max_lease_term_months,
            LeasingCompany.is_active,
            Company.name,
            Company.inn,
        )
        .join(Company, Company.id == LeasingCompany.company_id, isouter=True)
        .where(LeasingCompany.is_active.is_(True))
        .order_by(LeasingCompany.id.asc())
    )
    rows = (await session.execute(stmt)).all()
    return [
        {
            "id": row.id,
            "company_id": row.company_id,
            "name": row.name,
            "inn": row.inn,
            "average_down_payment_percent": row.average_down_payment_percent,
            "average_lease_term_months": row.average_lease_term_months,
            "average_markup_percent": row.average_markup_percent,
            "min_down_payment_percent": row.min_down_payment_percent,
            "max_lease_term_months": row.max_lease_term_months,
            "is_active": bool(row.is_active),
        }
        for row in rows
    ]

# ---------------------------------------------------------------------------
# LC resolution (role=leasing_company user → leasing_companies.id)
# ---------------------------------------------------------------------------

@timed_repository
async def resolve_lc_id_for_user(
    session: AsyncSession, user_id: UUID
) -> UUID | None:
    """Return ``leasing_companies.id`` (UUID) for the given ``user_id``.

    Two wiring paths exist historically:

    1. ``leasing_company_users`` — explicit user → LC mapping (preferred).
    2. ``users.company_id`` → ``leasing_companies.company_id`` (legacy).

    This compatibility mapping is not an access policy. Protected cabinet
    reads use ``list_readable_lc_bindings`` through the shared application
    access service, including fresh permissions and an exact company context.
    """
    direct_stmt = select(LeasingCompanyUser.leasing_company_id).where(
        LeasingCompanyUser.user_id == user_id
    )
    direct = (await session.execute(direct_stmt)).first()
    if direct is not None:
        return direct[0]
    user_row = await session.get(User, user_id)
    if user_row is None or user_row.company_id is None:
        return None
    fallback_stmt = select(LeasingCompany.id).where(
        LeasingCompany.company_id == user_row.company_id
    )
    fallback = (await session.execute(fallback_stmt)).first()
    if fallback is None:
        return None
    return fallback[0]


async def list_readable_lc_bindings(
    session: AsyncSession, *, user_id: UUID,
    company_id: UUID | None = None, leasing_company_id: UUID | None = None,
) -> list[dict[str, Any]]:
    """Fresh LC access projection; an explicit company permission deny wins.

    The three supported membership sources are user_companies, the explicit
    LC-user relation, and the legacy primary company. Deleted/inactive actors
    and companies never form a binding, even if their JWT is still valid.
    """
    explicit_lc_member = exists(select(LeasingCompanyUser.id).where(
        LeasingCompanyUser.user_id == User.id,
        LeasingCompanyUser.leasing_company_id == LeasingCompany.id,
    ))
    stmt = (
        select(LeasingCompany.id.label("leasing_company_id"), Company.id.label("company_id"))
        .select_from(LeasingCompany)
        .join(Company, Company.id == LeasingCompany.company_id)
        .join(User, User.id == user_id)
        .outerjoin(UserCompany, and_(UserCompany.user_id == User.id, UserCompany.company_id == Company.id))
        .where(
            User.role == "leasing_company", User.is_active.is_(True), User.deleted_at.is_(None),
            Company.company_type == "leasing_company", Company.is_active.is_(True),
            LeasingCompany.is_active.is_(True),
            or_(UserCompany.user_id.is_not(None), User.company_id == Company.id, explicit_lc_member),
            or_(UserCompany.user_id.is_(None), UserCompany.can_view_applications.is_(True)),
        )
        .order_by(LeasingCompany.id)
    )
    if company_id is not None:
        stmt = stmt.where(Company.id == company_id)
    if leasing_company_id is not None:
        stmt = stmt.where(LeasingCompany.id == leasing_company_id)
    return [dict(row._mapping) for row in (await session.execute(stmt)).all()]

# ---------------------------------------------------------------------------
# LC-application links
# ---------------------------------------------------------------------------

@timed_repository
async def get_link_by_id(
    session: AsyncSession, link_id: UUID, *, for_update: bool = False,
) -> dict[str, Any] | None:
    row = await session.get(
        LeasingCompanyApplication, link_id,
        with_for_update=for_update, populate_existing=for_update,
    )
    if row is None:
        return None
    return _lca_to_dict(row)

@timed_repository
async def get_link_for_app_and_lc(
    session: AsyncSession,
    *,
    application_id: uuid.UUID,
    leasing_company_id: UUID,
    for_update: bool = False,
) -> dict[str, Any] | None:
    stmt = select(LeasingCompanyApplication).where(
        LeasingCompanyApplication.application_id == application_id,
        LeasingCompanyApplication.leasing_company_id == leasing_company_id,
    )
    if for_update:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        return None
    return _lca_to_dict(row)


@timed_repository
async def get_link_for_app_and_lc_for_update(
    session: AsyncSession,
    *,
    application_id: uuid.UUID,
    leasing_company_id: UUID,
) -> dict[str, Any] | None:
    """Load an LCA under a transaction-scoped row lock."""
    stmt = (
        select(LeasingCompanyApplication)
        .where(
            LeasingCompanyApplication.application_id == application_id,
            LeasingCompanyApplication.leasing_company_id == leasing_company_id,
        )
        .with_for_update()
    )
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        return None
    return _lca_to_dict(row)


@timed_repository
async def list_links_for_app_and_lc(
    session: AsyncSession,
    *,
    application_id: uuid.UUID,
    leasing_company_id: UUID,
) -> list[dict[str, Any]]:
    stmt = (
        select(LeasingCompanyApplication)
        .where(
            LeasingCompanyApplication.application_id == application_id,
            LeasingCompanyApplication.leasing_company_id == leasing_company_id,
        )
        .order_by(LeasingCompanyApplication.id.asc())
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [_lca_to_dict(row) for row in rows]


@timed_repository
async def upsert_link_under_review(
    session: AsyncSession,
    *,
    application_id: uuid.UUID,
    leasing_company_id: UUID,
) -> UUID:
    """Ensure a link exists with status=under_review — returns id."""
    existing_stmt = select(LeasingCompanyApplication).where(
        LeasingCompanyApplication.application_id == application_id,
        LeasingCompanyApplication.leasing_company_id == leasing_company_id,
    )
    existing = (
        await session.execute(existing_stmt)
    ).scalar_one_or_none()
    if existing is not None:
        return existing.id
    row = LeasingCompanyApplication(
        application_id=application_id,
        leasing_company_id=leasing_company_id,
        status="under_review",
    )
    session.add(row)
    await session.flush()
    await history_repo.append_lca_status_history(
        session,
        lca_id=row.id,
        application_id=application_id,
        old_status=None,
        new_status="under_review",
    )
    return row.id


@timed_repository
async def create_link(
    session: AsyncSession,
    *,
    application_id: uuid.UUID,
    leasing_company_id: UUID | None,
    status: str,
    created_at: datetime | None = None,
) -> UUID:
    """Insert a leasing_company_applications row with an explicit status."""
    row = LeasingCompanyApplication(
        application_id=application_id,
        leasing_company_id=leasing_company_id,
        status=status,
    )
    if created_at is not None:
        cast("Any", row).created_at = created_at
    session.add(row)
    await session.flush()
    await history_repo.append_lca_status_history(
        session,
        lca_id=row.id,
        application_id=application_id,
        old_status=None,
        new_status=status,
    )
    return row.id


@timed_repository
async def update_link_status(
    session: AsyncSession,
    *,
    link_id: UUID,
    new_status: str,
    review_notes: str | None = None,
) -> bool:
    row = await session.get(LeasingCompanyApplication, link_id)
    if row is None:
        return False
    row.status = new_status
    if review_notes is not None:
        row.review_notes = review_notes
    cast("Any", row).updated_at = datetime.now(UTC)
    await session.flush()
    return True

@timed_repository
async def list_lca_statuses(
    session: AsyncSession, application_id: uuid.UUID
) -> list[str]:
    stmt = select(LeasingCompanyApplication.status).where(
        LeasingCompanyApplication.application_id == application_id
    )
    rows = (await session.execute(stmt)).all()
    return [str(r[0] or "") for r in rows]

# ---------------------------------------------------------------------------
# Application projection (read-only, scoped)
# ---------------------------------------------------------------------------

@timed_repository
async def get_application_projection(
    session: AsyncSession, application_id: uuid.UUID
) -> dict[str, Any] | None:
    row = await session.get(LeasingApplication, application_id)
    if row is None:
        return None
    return {
        "id": row.id,
        "company_id": row.company_id,
        "status": row.status,
        "selected_leasing_companies": list(row.selected_leasing_companies)
        if row.selected_leasing_companies is not None
        else [],
        "requested_documents": row.requested_documents,
    }

@timed_repository
async def count_applications_for_lc(
    session: AsyncSession,
    *,
    leasing_company_id: UUID,
    status: str | None = None,
    source_types: tuple[str, ...] = (),
    search: str | None = None,
) -> int:
    stmt = (
        select(func.count(LeasingCompanyApplication.id))
        .join(LeasingApplication, LeasingApplication.id == LeasingCompanyApplication.application_id)
        .where(LeasingCompanyApplication.leasing_company_id == leasing_company_id)
    )
    if status:
        stmt = stmt.where(LeasingCompanyApplication.status == status)
    stmt = stmt.where(*application_source_filters(source_types=source_types, search=search))
    result = await session.execute(stmt)
    return result.scalar() or 0


@timed_repository
async def list_applications_for_lc(
    session: AsyncSession,
    *,
    leasing_company_id: UUID,
    status: str | None = None,
    source_types: tuple[str, ...] = (),
    search: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """Applications for the LC review cabinet — filtered by link status.

    The Express endpoint paginated on the parent application set; here we
    return the rich link objects because the LC cabinet needs per-LC status.
    """
    sort_at = func.coalesce(
        LeasingCompanyApplication.updated_at,
        LeasingCompanyApplication.submitted_at,
        LeasingApplication.updated_at,
        LeasingApplication.created_at,
        LeasingCompanyApplication.created_at,
    )
    stmt = (
        select(
            LeasingCompanyApplication,
            LeasingApplication,
            Company.name.label("company_name"),
            Company.inn.label("company_inn"),
        )
        .join(
            LeasingApplication,
            LeasingApplication.id == LeasingCompanyApplication.application_id,
        )
        .join(
            Company,
            Company.id == LeasingApplication.company_id,
            isouter=True,
        )
        .where(
            LeasingCompanyApplication.leasing_company_id == leasing_company_id
        )
        .order_by(sort_at.desc(), LeasingApplication.created_at.desc())
    )
    if status:
        stmt = stmt.where(LeasingCompanyApplication.status == status)
    stmt = stmt.where(*application_source_filters(source_types=source_types, search=search))
    stmt = stmt.limit(limit).offset(offset)
    rows = (await session.execute(stmt)).all()

    app_ids = [app_row.id for _, app_row, _, _ in rows]
    vehicles_counts = await _vehicles_count_by_application(session, app_ids)
    docs_counts = await docs_repo.count_by_application_ids(
        session, application_ids=app_ids
    )

    out: list[dict[str, Any]] = []
    for lca_row, app_row, c_name, c_inn in rows:
        out.append(
            {
                "link": _lca_to_dict(lca_row),
                "application": {
                    "id": app_row.id,
                    "display_number": app_row.display_number,
                    "source_type": app_row.source_type,
                    "company_id": app_row.company_id,
                    "company_name": c_name,
                    "company_inn": c_inn,
                    "name": app_row.name,
                    "email": app_row.email,
                    "status": app_row.status,
                    "total_amount": app_row.total_amount,
                    "down_payment": app_row.down_payment,
                    "down_payment_percent": app_row.down_payment_percent,
                    "lease_term_months": app_row.lease_term_months,
                    "monthly_payment": app_row.monthly_payment,
                    "selected_leasing_companies": list(
                        app_row.selected_leasing_companies
                    )
                    if app_row.selected_leasing_companies is not None
                    else [],
                    "vehicles_count": vehicles_counts.get(app_row.id, 0),
                    "attached_documents_count": docs_counts.get(app_row.id, 0),
                    "created_at": app_row.created_at,
                    "updated_at": app_row.updated_at,
                },
            }
        )
    return out


@timed_repository
async def list_lc_applications_overview(
    session: AsyncSession,
    *,
    leasing_company_id: UUID,
    status: str | None = None,
    page: int = 1,
    limit: int = 20,
) -> dict[str, Any]:
    page = max(page, 1)
    limit = max(limit, 1)
    base_stmt = (
        select(LeasingApplication, LeasingCompanyApplication)
        .outerjoin(
            LeasingCompanyApplication,
            and_(
                LeasingCompanyApplication.application_id == LeasingApplication.id,
                LeasingCompanyApplication.leasing_company_id == leasing_company_id,
            ),
        )
    )
    count_stmt = (
        select(func.count(LeasingApplication.id))
        .outerjoin(
            LeasingCompanyApplication,
            and_(
                LeasingCompanyApplication.application_id == LeasingApplication.id,
                LeasingCompanyApplication.leasing_company_id == leasing_company_id,
            ),
        )
    )
    if status:
        base_stmt = base_stmt.where(LeasingCompanyApplication.status == status)
        count_stmt = count_stmt.where(LeasingCompanyApplication.status == status)
    else:
        base_stmt = base_stmt.where(LeasingCompanyApplication.id.is_not(None))
        count_stmt = count_stmt.where(LeasingCompanyApplication.id.is_not(None))

    total = int((await session.execute(count_stmt)).scalar() or 0)
    rows = (
        await session.execute(
            base_stmt.order_by(LeasingApplication.created_at.desc())
            .offset((page - 1) * limit)
            .limit(limit)
        )
    ).all()

    applications: list[dict[str, Any]] = []
    for la_row, lca_row in rows:
        app_dict = _leasing_application_overview_to_dict(la_row)
        lc_ids = app_dict.get("selected_leasing_companies") or []
        if lc_ids:
            company_stmt = (
                select(LeasingCompany.id, Company.name)
                .join(Company, Company.id == LeasingCompany.company_id, isouter=True)
                .where(LeasingCompany.id.in_(lc_ids))
            )
            company_result = await session.execute(company_stmt)
            app_dict["selected_companies_info"] = [
                {"company_id": row.id, "company_name": row.name}
                for row in company_result.all()
            ]
        else:
            app_dict["selected_companies_info"] = []
        applications.append({
            "application": app_dict,
            "link": _lca_to_dict(lca_row) if lca_row else None,
        })

    return {
        "applications": applications,
        "pagination": {
            "page": page,
            "limit": limit,
            "total": total,
            "pages": (total + limit - 1) // limit if limit else 0,
        },
    }


@timed_repository
async def list_lca_rows_for_actor(
    session: AsyncSession,
    *,
    actor_role: str,
    actor_company_id: UUID | None = None,
    actor_leasing_company_id: UUID | None = None,
    status: str | None = None,
    application_id: UUID | None = None,
    page: int = 1,
    limit: int = 20,
) -> dict[str, Any]:
    page = max(page, 1)
    limit = max(limit, 1)
    if (
        actor_role == "leasing_company"
        and actor_leasing_company_id is None
        and actor_company_id is not None
    ):
        resolved_lc_id = (
            await session.execute(
                select(LeasingCompany.id).where(
                    LeasingCompany.company_id == actor_company_id
                )
            )
        ).scalar_one_or_none()
        actor_leasing_company_id = resolved_lc_id or actor_company_id
    where_clause = _lca_actor_where_clause(
        actor_role=actor_role,
        actor_company_id=actor_company_id,
        actor_leasing_company_id=actor_leasing_company_id,
    )
    if where_clause is False:
        return _empty_lca_rows_result(page=page, limit=limit)

    leasing_company_alias = aliased(Company)
    count_stmt = (
        select(func.count(LeasingCompanyApplication.id))
        .select_from(LeasingCompanyApplication)
        .join(
            LeasingApplication,
            LeasingApplication.id == LeasingCompanyApplication.application_id,
        )
    )
    stmt = (
        select(
            LeasingCompanyApplication,
            LeasingApplication.display_number,
            LeasingApplication.status.label("application_status"),
            LeasingApplication.company_id,
            Company.name.label("company_name"),
            Company.inn.label("company_inn"),
            leasing_company_alias.name.label("leasing_company_name"),
            leasing_company_alias.inn.label("leasing_company_inn"),
        )
        .select_from(LeasingCompanyApplication)
        .join(
            LeasingApplication,
            LeasingApplication.id == LeasingCompanyApplication.application_id,
        )
        .join(Company, Company.id == LeasingApplication.company_id, isouter=True)
        .join(
            LeasingCompany,
            LeasingCompany.id == LeasingCompanyApplication.leasing_company_id,
            isouter=True,
        )
        .join(
            leasing_company_alias,
            leasing_company_alias.id == LeasingCompany.company_id,
            isouter=True,
        )
        .order_by(LeasingCompanyApplication.created_at.desc())
        .offset((page - 1) * limit)
        .limit(limit)
    )
    filters: list[Any] = []
    if where_clause is not None:
        filters.append(where_clause)
    if status:
        filters.append(LeasingCompanyApplication.status == status)
    if application_id is not None:
        filters.append(
            LeasingCompanyApplication.application_id == application_id
        )
    if filters:
        count_stmt = count_stmt.where(*filters)
        stmt = stmt.where(*filters)

    total = int((await session.execute(count_stmt)).scalar() or 0)
    rows = (await session.execute(stmt)).all()
    return {
        "items": [_lca_row_with_application_to_dict(row) for row in rows],
        "pagination": {
            "page": page,
            "limit": limit,
            "total": total,
            "pages": (total + limit - 1) // limit if limit else 0,
        },
    }


def _lca_actor_where_clause(
    *,
    actor_role: str,
    actor_company_id: UUID | None,
    actor_leasing_company_id: UUID | None,
) -> Any | bool | None:
    if actor_role in {"carcraft_employee", "distributor"}:
        return None
    if actor_role == "leasing_company":
        lc_id = actor_leasing_company_id or actor_company_id
        return (
            LeasingCompanyApplication.leasing_company_id == lc_id
            if lc_id is not None
            else False
        )
    if actor_role == "dealer":
        if actor_company_id is None:
            return False
        return or_(
            LeasingApplication.dealer_company_id == actor_company_id,
            and_(
                LeasingApplication.dealer_company_id.is_(None),
                LeasingApplication.company_id == actor_company_id,
            ),
            dealer_child_ownership_clause(
                LeasingApplication.id,
                actor_company_id,
            ),
        )
    if actor_role == "client":
        return (
            LeasingApplication.company_id == actor_company_id
            if actor_company_id is not None
            else False
        )
    return False


def _empty_lca_rows_result(*, page: int, limit: int) -> dict[str, Any]:
    return {
        "items": [],
        "pagination": {
            "page": page,
            "limit": limit,
            "total": 0,
            "pages": 0,
        },
    }


def _optional_isoformat(value: Any) -> str | None:
    if value is None:
        return None
    isoformat = getattr(value, "isoformat", None)
    return str(isoformat()) if callable(isoformat) else str(value)


def _leasing_application_overview_to_dict(row: LeasingApplication) -> dict[str, Any]:
    return {
        "id": row.id,
        "company_id": row.company_id,
        "dealer_company_id": row.dealer_company_id,
        "name": row.name,
        "email": row.email,
        "status": row.status,
        "total_amount": str(row.total_amount) if row.total_amount else None,
        "down_payment": str(row.down_payment) if row.down_payment else None,
        "down_payment_percent": (
            str(row.down_payment_percent) if row.down_payment_percent else None
        ),
        "lease_term_months": row.lease_term_months,
        "monthly_payment": str(row.monthly_payment) if row.monthly_payment else None,
        "total_cost": str(row.total_cost) if row.total_cost else None,
        "markup": str(row.markup) if row.markup else None,
        "rate": str(row.rate) if row.rate else None,
        "total_interest": str(row.total_interest) if row.total_interest else None,
        "buyout_amount": str(row.buyout_amount) if row.buyout_amount else None,
        "vat_refund": str(row.vat_refund) if row.vat_refund else None,
        "profit_tax_savings": (
            str(row.profit_tax_savings) if row.profit_tax_savings else None
        ),
        "total_savings": str(row.total_savings) if row.total_savings else None,
        "selected_leasing_companies": row.selected_leasing_companies,
        "leasing_company_comments": row.leasing_company_comments,
        "requested_documents": row.requested_documents,
        "questionnaire_completed": row.questionnaire_completed,
        "questionnaire_progress": row.questionnaire_progress,
        "current_stage": row.current_stage,
        "display_number": row.display_number,
        "source_type": row.source_type,
        "created_at": _optional_isoformat(row.created_at),
        "updated_at": _optional_isoformat(row.updated_at),
    }


def _lca_row_with_application_to_dict(row: Any) -> dict[str, Any]:
    (
        lca,
        display_number,
        application_status,
        company_id,
        company_name,
        company_inn,
        leasing_company_name,
        leasing_company_inn,
    ) = row
    result = _lca_to_dict(lca)
    result.update(
        {
            "display_number": display_number,
            "application_status": application_status,
            "company_id": company_id,
            "company_name": company_name,
            "company_inn": company_inn,
            "leasing_company_name": leasing_company_name,
            "leasing_company_inn": leasing_company_inn,
        }
    )
    return result

@timed_repository
async def _vehicles_count_by_application(
    session: AsyncSession, application_ids: list[UUID]
) -> dict[UUID, int]:
    if not application_ids:
        return {}
    stmt = (
        select(
            ApplicationVehicle.application_id,
            func.count(ApplicationVehicle.id),
        )
        .where(ApplicationVehicle.application_id.in_(application_ids))
        .group_by(ApplicationVehicle.application_id)
    )
    return {
        row[0]: int(row[1])
        for row in (await session.execute(stmt)).all()
    }

# ---------------------------------------------------------------------------
# Comments
# ---------------------------------------------------------------------------

@timed_repository
async def add_application_comment(
    session: AsyncSession,
    *,
    application_id: uuid.UUID,
    comment_type: str,
    comment_text: str,
    created_by: UUID | None,
) -> UUID:
    row = LeasingApplicationComment(
        leasing_application_id=application_id,
        comment_type=comment_type,
        comment_text=comment_text,
        created_by=created_by,
    )
    session.add(row)
    await session.flush()
    return row.id

# ---------------------------------------------------------------------------
# LeasingApplication.status cascade helper
# ---------------------------------------------------------------------------

@timed_repository
async def update_parent_application_status(
    session: AsyncSession,
    *,
    application_id: uuid.UUID,
    new_status: str,
) -> bool:
    row = await session.get(LeasingApplication, application_id)
    if row is None:
        return False
    row.status = new_status
    cast("Any", row).updated_at = datetime.now(UTC)
    await session.flush()
    return True

@timed_repository
async def attach_response_pdf(
    session: AsyncSession,
    *,
    link_id: UUID,
    s3_key: str,
    file_name: str,
    file_size: int,
) -> bool:
    row = await session.get(LeasingCompanyApplication, link_id)
    if row is None:
        return False
    row.response_pdf_s3_key = s3_key
    row.response_pdf_file_name = file_name
    row.response_pdf_size = file_size
    cast("Any", row).response_pdf_uploaded_at = datetime.now(UTC)
    cast("Any", row).updated_at = datetime.now(UTC)
    await session.flush()
    return True

@timed_repository
async def detach_response_pdf(
    session: AsyncSession, *, link_id: UUID
) -> dict[str, Any] | None:
    """Remove the PDF reference from the LCA, returning the prior s3 key."""
    row = await session.get(LeasingCompanyApplication, link_id)
    if row is None:
        return None
    snapshot = {
        "s3_key": row.response_pdf_s3_key,
        "file_name": row.response_pdf_file_name,
    }
    row.response_pdf_s3_key = None
    row.response_pdf_file_name = None
    row.response_pdf_size = None
    row.response_pdf_uploaded_at = None
    cast("Any", row).updated_at = datetime.now(UTC)
    await session.flush()
    return snapshot

@timed_repository
async def submit_decision(
    session: AsyncSession,
    *,
    link_id: UUID,
    new_status: str,
    decision_comment: str | None,
) -> bool:
    row = await session.get(LeasingCompanyApplication, link_id)
    if row is None:
        return False
    row.status = new_status
    row.decision_comment = decision_comment
    now = datetime.now(UTC)
    cast("Any", row).submitted_at = now
    cast("Any", row).updated_at = now
    await session.flush()
    return True

@timed_repository
async def submit_prescoring(
    session: AsyncSession,
    *,
    link_id: UUID,
    decision_comment: str | None,
) -> bool:
    """Persist a preliminary-КП submission.

    Sets status to ``prescoring`` and stores the decision comment, but does
    NOT mark the LCA as finally submitted (``submitted_at`` stays null) —
    the LC must still be able to upsert the final КП afterwards.
    """
    row = await session.get(LeasingCompanyApplication, link_id)
    if row is None:
        return False
    row.status = LCA_STATUS_APPROVED_SCORING
    row.decision_comment = decision_comment
    cast("Any", row).updated_at = datetime.now(UTC)
    await session.flush()
    return True

@timed_repository
async def get_application_full(
    session: AsyncSession, application_id: uuid.UUID
) -> dict[str, Any] | None:
    """Return the parent leasing application with the full parameter set.

    Used by the LC cabinet to display original (requested) parameters and
    by the proposal pre-fill flow.
    """
    row = await session.get(LeasingApplication, application_id)
    if row is None:
        return None
    return {
        "id": row.id,
        "display_number": row.display_number,
        "source_type": row.source_type,
        "company_id": row.company_id,
        "name": row.name,
        "email": row.email,
        "status": row.status,
        "total_amount": row.total_amount,
        "down_payment": row.down_payment,
        "down_payment_percent": row.down_payment_percent,
        "lease_term_months": row.lease_term_months,
        "monthly_payment": row.monthly_payment,
        "total_cost": row.total_cost,
        "markup": row.markup,
        "rate": row.rate,
        "total_interest": row.total_interest,
        "buyout_amount": row.buyout_amount,
        "vat_refund": row.vat_refund,
        "profit_tax_savings": row.profit_tax_savings,
        "total_savings": row.total_savings,
        "selected_leasing_companies": list(row.selected_leasing_companies)
        if row.selected_leasing_companies is not None
        else [],
        "requested_documents": row.requested_documents,
    }

@timed_repository
async def list_submitted_responses_for_application(
    session: AsyncSession, application_id: uuid.UUID
) -> list[dict[str, Any]]:
    """All LCAs for an application that the client should see.

    Includes both fully-submitted LCAs (final approve / reject) and LCAs
    that have issued a preliminary KP (status=prescoring) — those don't
    set submitted_at because the LC is still working on the final, but the
    client must still see the preliminary offer.

    Joins the leasing-company display info from the ``leasing_companies``
    + ``companies`` tables so the client side can render the LC name
    without further round-trips.
    """
    from sqlalchemy import or_

    stmt = (
        select(
            LeasingCompanyApplication,
            LeasingCompany.id.label("lc_id"),
            Company.name.label("lc_name"),
            Company.inn.label("lc_inn"),
        )
        .join(
            LeasingCompany,
            LeasingCompany.id == LeasingCompanyApplication.leasing_company_id,
            isouter=True,
        )
        .join(Company, Company.id == LeasingCompany.company_id, isouter=True)
        .where(
            LeasingCompanyApplication.application_id == application_id,
            or_(
                LeasingCompanyApplication.submitted_at.is_not(None),
                LeasingCompanyApplication.status.in_(
                    [
                        LCA_STATUS_APPROVED_SCORING,
                        LCA_STATUS_APPROVED_SCORING_ANOTHER_COND,
                    ]
                ),
            ),
        )
        .order_by(
            LeasingCompanyApplication.submitted_at.is_(None).asc(),
            LeasingCompanyApplication.submitted_at.desc(),
            LeasingCompanyApplication.id.desc(),
        )
    )
    rows = (await session.execute(stmt)).all()
    out: list[dict[str, Any]] = []
    for lca_row, lc_id, lc_name, lc_inn in rows:
        record = _lca_to_dict(lca_row)
        record["leasing_company"] = {
            "id": lc_id,
            "name": lc_name,
            "inn": lc_inn,
        }
        out.append(record)
    return out

@timed_repository
async def get_application_owner_user_id(
    session: AsyncSession, application_id: uuid.UUID
) -> UUID | None:
    """Resolve the application's "owner" user — the dealer/client who created
    it. Falls back to the first user attached to the application's
    ``company_id`` so notifications still reach a human when the dealer ref
    is missing (legacy rows).
    """
    app_row = await session.get(LeasingApplication, application_id)
    if app_row is None:
        return None
    stmt = select(User.id).where(User.company_id == app_row.company_id).limit(1)
    res = (await session.execute(stmt)).first()
    return res[0] if res is not None else None

@timed_repository
async def get_user_email(session: AsyncSession, user_id: UUID) -> str | None:
    row = await session.get(User, user_id)
    if row is None:
        return None
    email = getattr(row, "email", None)
    return str(email) if email else None

@timed_repository
async def get_leasing_company_display_name(
    session: AsyncSession, leasing_company_id: UUID
) -> str | None:
    stmt = (
        select(Company.name)
        .join(LeasingCompany, LeasingCompany.company_id == Company.id)
        .where(LeasingCompany.id == leasing_company_id)
    )
    row = (await session.execute(stmt)).first()
    return str(row[0]) if row is not None else None

@timed_repository
async def lc_user_has_review_access_to_company(
    session: AsyncSession, *, user_id: UUID, company_id: UUID
) -> bool:
    """True if the LC user has an LCA on any application whose
    ``company_id`` matches — i.e. the user is reviewing this client and
    is therefore allowed to read the client's company profile.
    """
    user_lc_id = await resolve_lc_id_for_user(session, user_id)
    if user_lc_id is None:
        return False
    stmt = (
        select(LeasingCompanyApplication.id)
        .join(
            LeasingApplication,
            LeasingApplication.id == LeasingCompanyApplication.application_id,
        )
        .where(
            LeasingCompanyApplication.leasing_company_id == user_lc_id,
            LeasingApplication.company_id == company_id,
        )
        .limit(1)
    )
    return (await session.execute(stmt)).first() is not None

__all__ = [
    "add_application_comment",
    "attach_response_pdf",
    "detach_response_pdf",
    "get_application_full",
    "get_application_owner_user_id",
    "get_application_projection",
    "get_leasing_company_display_name",
    "get_link_by_id",
    "get_link_for_app_and_lc",
    "get_link_for_app_and_lc_for_update",
    "get_user_email",
    "lc_user_has_review_access_to_company",
    "list_active_leasing_companies",
    "list_applications_for_lc",
    "list_lca_statuses",
    "list_links_for_app_and_lc",
    "list_submitted_responses_for_application",
    "resolve_lc_id_for_user",
    "submit_decision",
    "submit_prescoring",
    "update_link_status",
    "update_parent_application_status",
    "upsert_link_under_review",
]
