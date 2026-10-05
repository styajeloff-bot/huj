"""Admin-side applications listing + LC assignment helpers.

Thin read wrapper over ``leasing_applications`` that allows full-scope
listing (no role filter) with pagination + search + status filter. For
writes (status changes, LC row creation) the admin handlers reuse
``application_repository`` (``upsert_lc_links``, ``update_selected_leasing_companies``).
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from typing import cast as type_cast
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.models.applications import (
    ApplicationVehicle,
    LeasingApplication,
    LeasingCompanyApplication,
    LeasingProposal,
)
from infrastructure.models.companies import Company, LeasingCompany
from infrastructure.models.special_equipment_commerce import (
    SpecialEquipmentApplicationItem,
)
from infrastructure.models.users import User
from infrastructure.repositories.application_source_filters import (
    application_source_filters,
)
from infrastructure.repository_timing import timed_repository


def _app_to_dict(
    row: LeasingApplication,
    phone: str | None = None,
    company_name: str | None = None,
    company_inn: str | None = None,
) -> dict[str, Any]:
    return {
        "id": row.id,
        "display_number": row.display_number,
        "source_type": row.source_type,
        "company_id": row.company_id,
        "name": row.name,
        "email": row.email,
        "phone": phone,
        "company_name": company_name,
        "company_inn": company_inn,
        "status": row.status,
        "total_amount": row.total_amount,
        "down_payment": row.down_payment,
        "down_payment_percent": row.down_payment_percent,
        "lease_term_months": row.lease_term_months,
        "monthly_payment": row.monthly_payment,
        "selected_leasing_companies": list(row.selected_leasing_companies)
        if row.selected_leasing_companies is not None
        else [],
        "current_stage": row.current_stage,
        "vehicles_count": 0,
        "total_vehicles_price": Decimal("0"),
        "items_count": 0,
        "total_items_price": Decimal("0"),
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _lca_to_dict(
    row: LeasingCompanyApplication,
    *,
    leasing_company_name: str | None = None,
    leasing_company_inn: str | None = None,
) -> dict[str, Any]:
    return {
        "id": row.id,
        "application_id": row.application_id,
        "leasing_company_id": row.leasing_company_id,
        "status": row.status,
        "review_notes": row.review_notes,
        "decision_comment": row.decision_comment,
        "response_pdf_file_name": row.response_pdf_file_name,
        "response_pdf_size": row.response_pdf_size,
        "response_pdf_uploaded_at": row.response_pdf_uploaded_at,
        "submitted_at": row.submitted_at,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        "leasing_company": {
            "id": row.leasing_company_id,
            "name": leasing_company_name,
            "inn": leasing_company_inn,
        },
    }


def _proposal_to_dict(row: LeasingProposal) -> dict[str, Any]:
    return {
        "id": row.id,
        "leasing_company_application_id": row.leasing_company_application_id,
        "kind": row.kind,
        "position": row.position,
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
        "client_decision_action": row.client_decision_action,
        "client_decision_at": row.client_decision_at,
        "client_decision_comment": row.client_decision_comment,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


@timed_repository
async def list_all(
    session: AsyncSession,
    *,
    page: int = 1,
    limit: int = 20,
    status: str | None = None,
    search: str | None = None,
    source_types: tuple[str, ...] = (),
) -> tuple[list[dict[str, Any]], int]:
    """Full listing — employee scope, no role filter."""
    conditions: list[Any] = []
    if status:
        conditions.append(LeasingApplication.status == status)
    conditions.extend(application_source_filters(source_types=source_types, search=search))

    where_clause: Any = None
    if conditions:
        from sqlalchemy import and_

        where_clause = and_(*conditions)

    count_stmt = select(func.count(LeasingApplication.id))
    if where_clause is not None:
        count_stmt = count_stmt.where(where_clause)
    total = int((await session.execute(count_stmt)).scalar() or 0)

    list_stmt = (
        select(LeasingApplication, User.phone, Company.name, Company.inn)
        .select_from(LeasingApplication)
        .outerjoin(User, User.id == LeasingApplication.created_by)
        .outerjoin(Company, Company.id == LeasingApplication.company_id)
        .order_by(LeasingApplication.created_at.desc().nulls_last())
    )
    if where_clause is not None:
        list_stmt = list_stmt.where(where_clause)
    list_stmt = list_stmt.offset((max(page, 1) - 1) * max(limit, 1)).limit(
        max(limit, 1)
    )
    rows = (await session.execute(list_stmt)).all()

    items: list[dict[str, Any]] = []
    for row in rows:
        app_row, creator_phone, company_name, company_inn = row
        item = _app_to_dict(app_row, phone=creator_phone, company_name=company_name, company_inn=company_inn)
        count, total_price = await _vehicles_count_and_total(session, app_row.id)
        item["vehicles_count"] = count
        # The persisted line total includes selected equipment and services.
        item["total_vehicles_price"] = total_price
        item["items_count"] = count
        item["total_items_price"] = total_price
        item["selected_companies_info"] = await _list_companies_info(
            session, item["selected_leasing_companies"]
        )
        items.append(item)
    return items, total


@timed_repository
async def get_detail_base(
    session: AsyncSession, application_id: uuid.UUID
) -> dict[str, Any] | None:
    stmt = (
        select(LeasingApplication, User.phone, Company.name, Company.inn)
        .select_from(LeasingApplication)
        .outerjoin(User, User.id == LeasingApplication.created_by)
        .outerjoin(Company, Company.id == LeasingApplication.company_id)
        .where(LeasingApplication.id == application_id)
    )
    row = (await session.execute(stmt)).one_or_none()
    if row is None:
        return None

    app_row, creator_phone, company_name, company_inn = row
    item = _app_to_dict(
        app_row,
        phone=creator_phone,
        company_name=company_name,
        company_inn=company_inn,
    )
    count, total_price = await _vehicles_count_and_total(session, app_row.id)
    item["vehicles_count"] = count
    item["total_vehicles_price"] = total_price
    item["items_count"] = count
    item["total_items_price"] = total_price
    item["selected_companies_info"] = await _list_companies_info(
        session, item["selected_leasing_companies"]
    )
    return item


@timed_repository
async def list_lca_details(
    session: AsyncSession, application_id: uuid.UUID
) -> list[dict[str, Any]]:
    stmt = (
        select(
            LeasingCompanyApplication,
            Company.name.label("leasing_company_name"),
            Company.inn.label("leasing_company_inn"),
        )
        .select_from(LeasingCompanyApplication)
        .outerjoin(
            LeasingCompany,
            LeasingCompany.id == LeasingCompanyApplication.leasing_company_id,
        )
        .outerjoin(Company, Company.id == LeasingCompany.company_id)
        .where(LeasingCompanyApplication.application_id == application_id)
        .order_by(LeasingCompanyApplication.created_at.asc().nulls_last(), LeasingCompanyApplication.id.asc())
    )
    rows = (await session.execute(stmt)).all()
    return [
        _lca_to_dict(
            lca,
            leasing_company_name=leasing_company_name,
            leasing_company_inn=leasing_company_inn,
        )
        for lca, leasing_company_name, leasing_company_inn in rows
    ]


@timed_repository
async def list_proposals_by_lca_ids(
    session: AsyncSession, lca_ids: list[UUID]
) -> list[dict[str, Any]]:
    if not lca_ids:
        return []

    stmt = (
        select(LeasingProposal)
        .where(LeasingProposal.leasing_company_application_id.in_(lca_ids))
        .order_by(
            LeasingProposal.leasing_company_application_id.asc(),
            LeasingProposal.kind.asc(),
            LeasingProposal.id.asc(),
        )
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [_proposal_to_dict(row) for row in rows]


@timed_repository
async def _vehicles_count_and_total(
    session: AsyncSession, application_id: uuid.UUID
) -> tuple[int, Decimal]:
    vehicle_stmt = select(
        func.coalesce(func.sum(func.coalesce(ApplicationVehicle.quantity, 1)), 0),
        func.coalesce(
            func.sum(
                func.coalesce(
                    func.nullif(
                        ApplicationVehicle.total_price,
                        0,
                    ),
                    func.nullif(
                        ApplicationVehicle.unit_price * func.coalesce(ApplicationVehicle.quantity, 1),
                        0,
                    ),
                    0,
                )
            ),
            0,
        ),
    ).where(
        ApplicationVehicle.application_id == application_id,
        or_(
            ApplicationVehicle.car_status.in_(("active", "confirmed", "replacement")),
            ApplicationVehicle.car_status.is_(None),
        ),
    )
    v_row = (await session.execute(vehicle_stmt)).one()
    v_count = int(v_row[0] or 0)
    v_total = Decimal(str(v_row[1] or 0))

    se_stmt = select(
        func.coalesce(func.count(SpecialEquipmentApplicationItem.id), 0),
        func.coalesce(
            func.sum(
                func.coalesce(
                    func.nullif(
                        SpecialEquipmentApplicationItem.total_price,
                        0,
                    ),
                    func.nullif(
                        SpecialEquipmentApplicationItem.unit_price,
                        0,
                    ),
                    0,
                )
            ),
            0,
        ),
    ).where(
        SpecialEquipmentApplicationItem.application_id == application_id,
        SpecialEquipmentApplicationItem.item_status.in_(("active", "reserved")),
        ~sa.exists().where(
            ApplicationVehicle.application_id == SpecialEquipmentApplicationItem.application_id,
            ApplicationVehicle.product_id == SpecialEquipmentApplicationItem.product_id,
        ),
    )
    se_row = (await session.execute(se_stmt)).one()
    se_count = int(se_row[0] or 0)
    se_total = Decimal(str(se_row[1] or 0))

    return v_count + se_count, v_total + se_total


@timed_repository
async def _list_companies_info(
    session: AsyncSession, leasing_company_ids: list[UUID]
) -> list[dict[str, Any]]:
    if not leasing_company_ids:
        return []
    stmt = (
        select(LeasingCompany.id, Company.name)
        .join(Company, Company.id == LeasingCompany.company_id, isouter=True)
        .where(LeasingCompany.id.in_(leasing_company_ids))
    )
    result = await session.execute(stmt)
    return [
        {"company_id": row.id, "company_name": row.name}
        for row in result.all()
    ]


@timed_repository
async def update_selected_leasing_companies(
    session: AsyncSession,
    application_id: uuid.UUID,
    *,
    leasing_company_ids: list[UUID],
) -> bool:
    """Replace the ``selected_leasing_companies`` array on the row."""
    row = await session.get(LeasingApplication, application_id)
    if row is None:
        return False
    row.selected_leasing_companies = list(leasing_company_ids)
    type_cast("Any", row).updated_at = datetime.now(UTC)
    await session.flush()
    return True
