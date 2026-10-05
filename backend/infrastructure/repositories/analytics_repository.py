"""Analytics repository — read-only ClickHouse queries for LC dashboard.

Presentation layer must never import ``query_clickhouse`` directly.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import Float, and_, create_engine, distinct, func, select, type_coerce

from infrastructure.clickhouse_readonly import query_clickhouse
from infrastructure.models.clickhouse import (
    DMLKApplicationFunnel,
    DMLKProposals,
    DWHApplicationVehicles,
    DWHDocuments,
    DWHExchangeBids,
    DWHExchangeRequests,
    DWHLeasingCompanyApplications,
    DWHUsers,
    DWHVehicles,
)
from infrastructure.settings import settings

# Table aliases
f = DMLKApplicationFunnel.__table__
p = DMLKProposals.__table__
dwh_lca = DWHLeasingCompanyApplications.__table__
d = DWHDocuments.__table__
av = DWHApplicationVehicles.__table__
v = DWHVehicles.__table__
er = DWHExchangeRequests.__table__
eb = DWHExchangeBids.__table__
u = DWHUsers.__table__

_engine = create_engine(settings.clickhouse_dsn)


def _safe_int(value: Any) -> int:
    if value is None:
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _safe_float(value: Any) -> float:
    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _format_day(value: Any) -> str:
    if hasattr(value, "strftime"):
        return str(value.strftime("%d.%m"))
    return str(value)


def _iso(value: Any) -> str:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


async def _execute(stmt: Any) -> list[dict[str, Any]]:
    compiled = stmt.compile(
        dialect=_engine.dialect,
        compile_kwargs={"literal_binds": False, "render_postcompile": True},
    )
    return await query_clickhouse(str(compiled), compiled.params)


# ---------------------------------------------------------------------------
# Application funnel helpers
# ---------------------------------------------------------------------------
def _app_from_obj(filters: dict[str, Any]) -> tuple[Any, bool]:
    """Application funnel + employee filter joins dwh_lca for employee verification."""
    from_obj = f
    has_dwh = False
    if filters.get("employees"):
        from_obj = from_obj.join(
            dwh_lca,
            and_(
                dwh_lca.c.application_id == f.c.application_id,
                dwh_lca.c.leasing_company_id == f.c.leasing_company_id,
            ),
        ).join(u, u.c.company_id == dwh_lca.c.dealer_company_id)
        has_dwh = True
    return from_obj, has_dwh


def _app_conditions(role: str, scope_id: UUID, filters: dict[str, Any]) -> list[Any]:
    conditions = []
    if role == "leasing_company":
        conditions.append(f.c.leasing_company_id == scope_id)
    else:
        conditions.append(f.c.dealer_id == scope_id)

    period_from = filters.get("period_from")
    if period_from:
        conditions.append(f.c.created_at >= _iso(period_from))
    period_to = filters.get("period_to")
    if period_to:
        conditions.append(f.c.created_at <= _iso(period_to))

    statuses = filters.get("statuses")
    if statuses:
        conditions.append(f.c.lca_status.in_(statuses))

    dealers = filters.get("dealers")
    if dealers:
        conditions.append(f.c.dealer_company_id.in_(dealers))

    marks = filters.get("marks")
    if marks:
        conditions.append(f.c.vehicle_mark_id.in_(marks))

    employees = filters.get("employees")
    if employees:
        conditions.append(u.c.user_id.in_(employees))

    return conditions


# ---------------------------------------------------------------------------
# Proposal helpers
# ---------------------------------------------------------------------------
def _proposal_from_obj(filters: dict[str, Any]) -> tuple[Any, bool]:
    from_obj = p
    has_dwh = False
    needs_funnel = bool(filters.get("dealers") or filters.get("marks"))
    needs_la = bool(filters.get("employees"))
    if needs_funnel:
        from_obj = from_obj.join(f, f.c.application_id == p.c.application_id)
    if needs_la:
        from_obj = from_obj.join(
            dwh_lca,
            and_(
                dwh_lca.c.application_id == p.c.application_id,
                dwh_lca.c.leasing_company_id == p.c.leasing_company_id,
            ),
        ).join(u, u.c.company_id == dwh_lca.c.dealer_company_id)
        has_dwh = True
    return from_obj, has_dwh


def _proposal_conditions(
    role: str, scope_id: UUID, filters: dict[str, Any]
) -> list[Any]:
    conditions = []
    if role == "leasing_company":
        conditions.append(p.c.leasing_company_id == scope_id)
    else:
        conditions.append(p.c.dealer_id == scope_id)

    period_from = filters.get("period_from")
    if period_from:
        conditions.append(p.c.proposal_created_at >= _iso(period_from))
    period_to = filters.get("period_to")
    if period_to:
        conditions.append(p.c.proposal_created_at <= _iso(period_to))

    statuses = filters.get("statuses")
    if statuses:
        conditions.append(p.c.client_decision_action.in_(statuses))

    dealers = filters.get("dealers")
    if dealers:
        conditions.append(f.c.dealer_company_id.in_(dealers))

    marks = filters.get("marks")
    if marks:
        conditions.append(f.c.vehicle_mark_id.in_(marks))

    employees = filters.get("employees")
    if employees:
        conditions.append(u.c.user_id.in_(employees))

    return conditions


# ---------------------------------------------------------------------------
# Document helpers
# ---------------------------------------------------------------------------
def _doc_from_obj(role: str, filters: dict[str, Any]) -> tuple[Any, bool]:
    from_obj = d
    has_dwh = True
    needs_la = bool(
        filters.get("dealers") or filters.get("marks") or role == "distributor"
    )
    if needs_la:
        from_obj = from_obj.join(
            dwh_lca, dwh_lca.c.application_id == d.c.related_application_id
        )
    if filters.get("marks"):
        from_obj = from_obj.join(
            av, av.c.application_id == d.c.related_application_id, isouter=True
        )
        from_obj = from_obj.join(
            v, v.c.vehicle_id == av.c.vehicle_id, isouter=True
        )
    return from_obj, has_dwh


def _doc_conditions(role: str, scope_id: UUID, filters: dict[str, Any]) -> list[Any]:
    conditions = []
    if role == "leasing_company":
        conditions.append(d.c.approved_by_leasing_company == scope_id)

    period_from = filters.get("period_from")
    if period_from:
        conditions.append(d.c.created_at >= _iso(period_from))
    period_to = filters.get("period_to")
    if period_to:
        conditions.append(d.c.created_at <= _iso(period_to))

    statuses = filters.get("statuses")
    if statuses:
        conditions.append(d.c.status.in_(statuses))

    employees = filters.get("employees")
    if employees:
        conditions.append(d.c.verified_by.in_(employees))

    dealers = filters.get("dealers")
    if dealers:
        conditions.append(dwh_lca.c.dealer_company_id.in_(dealers))

    marks = filters.get("marks")
    if marks:
        conditions.append(v.c.mark_id.in_(marks))

    return conditions


# ---------------------------------------------------------------------------
# Exchange helpers
# ---------------------------------------------------------------------------
def _exchange_from_obj(role: str, filters: dict[str, Any]) -> tuple[Any, bool]:
    from_obj = er
    has_dwh = True
    if role == "leasing_company":
        from_obj = from_obj.join(u, u.c.user_id == er.c.lc_user_id)
    needs_v = bool(
        filters.get("dealers") or filters.get("marks") or role == "distributor"
    )
    if needs_v:
        from_obj = from_obj.join(
            v, v.c.vehicle_id == er.c.vehicle_id, isouter=True
        )
    return from_obj, has_dwh


def _exchange_conditions(
    role: str, scope_id: UUID, filters: dict[str, Any]
) -> list[Any]:
    conditions = []
    if role == "leasing_company":
        conditions.append(u.c.company_id == scope_id)
    else:
        conditions.append(v.c.dealer_id == scope_id)

    period_from = filters.get("period_from")
    if period_from:
        conditions.append(er.c.created_at >= _iso(period_from))
    period_to = filters.get("period_to")
    if period_to:
        conditions.append(er.c.created_at <= _iso(period_to))

    statuses = filters.get("statuses")
    if statuses:
        conditions.append(er.c.status.in_(statuses))

    employees = filters.get("employees")
    if employees:
        conditions.append(er.c.lc_user_id.in_(employees))

    dealers = filters.get("dealers")
    if dealers:
        conditions.append(v.c.dealer_id.in_(dealers))

    marks = filters.get("marks")
    if marks:
        conditions.append(v.c.mark_id.in_(marks))

    return conditions


# ---------------------------------------------------------------------------
# Overview
# ---------------------------------------------------------------------------
async def get_overview_data(
    role: str, scope_id: UUID, filters: dict[str, Any]
) -> dict[str, Any]:
    from_obj, has_dwh = _app_from_obj(filters)
    conditions = _app_conditions(role, scope_id, filters)

    kpi_stmt = (
        select(
            func.count().label("total"),
            func.countIf(f.c.lca_status == "under_review").label("new_cnt"),
            func.countIf(
                f.c.lca_status.in_(
                    (
                        "under_review",
                        "under_review_with_docs",
                        "approved_scoring",
                        "approved_scoring_another_cond",
                        "documents_required",
                    )
                )
            ).label("in_review_cnt"),
            func.countIf(
                f.c.lca_status.in_(("approved_final", "approved_final_another_cond"))
            ).label("approved_cnt"),
            func.countIf(f.c.lca_status == "deal").label("issued_cnt"),
            func.countIf(
                f.c.lca_status.in_(("rejected_prescoring", "rejected_approved", "closed"))
            ).label("rejected_cnt"),
            func.sumIf(
                f.c.total_amount, f.c.lca_status.in_(("approved_final", "approved_final_another_cond"))
            ).label("approved_volume"),
            func.sumIf(f.c.total_amount, f.c.lca_status == "deal").label(
                "issued_volume"
            ),
        )
        .select_from(from_obj)
        .where(and_(*conditions))
    )
    if has_dwh:
        kpi_stmt = kpi_stmt.suffix_with("SETTINGS final = 1")

    day_expr = func.toDate(f.c.created_at).label("day")
    dynamics_stmt = (
        select(
            day_expr,
            func.countIf(f.c.lca_status == "under_review").label("new_cnt"),
            func.countIf(
                f.c.lca_status.in_(("approved_final", "approved_final_another_cond"))
            ).label("approved_cnt"),
            func.countIf(f.c.lca_status == "deal").label("issued_cnt"),
        )
        .select_from(from_obj)
        .where(and_(*conditions))
        .group_by(day_expr)
        .order_by(day_expr)
    )
    if has_dwh:
        dynamics_stmt = dynamics_stmt.suffix_with("SETTINGS final = 1")

    total_expr = func.count().label("cnt")
    status_stmt = (
        select(
            f.c.lca_status.label("status"),
            total_expr,
        )
        .select_from(from_obj)
        .where(and_(*conditions))
        .group_by(f.c.lca_status)
        .order_by(total_expr.desc())
    )
    if has_dwh:
        status_stmt = status_stmt.suffix_with("SETTINGS final = 1")

    tat_conditions = list(conditions)
    tat_conditions.append(
        f.c.lca_status.in_(
            (
                "under_review",
                "under_review_with_docs",
                "approved_final",
                "approved_final_another_cond",
                "rejected_prescoring",
                "rejected_approved",
                "closed",
                "deal",
            )
        )
    )
    avg_tat_expr = func.round(
        func.avgIf(
            func.dateDiff(
                "day",
                func.assumeNotNull(f.c.created_at),
                func.assumeNotNull(f.c.approved_at),
            ),
            f.c.approved_at.is_not(None),
        ),
        2,
    ).label("avg_tat")
    tat_stmt = (
        select(
            f.c.lca_status.label("status"),
            avg_tat_expr,
        )
        .select_from(from_obj)
        .where(and_(*tat_conditions))
        .group_by(f.c.lca_status)
        .order_by(avg_tat_expr.desc())
    )
    if has_dwh:
        tat_stmt = tat_stmt.suffix_with("SETTINGS final = 1")

    kpi_rows = await _execute(kpi_stmt)
    dynamics_rows = await _execute(dynamics_stmt)
    status_rows = await _execute(status_stmt)
    tat_rows = await _execute(tat_stmt)

    return {
        "kpi": kpi_rows[0] if kpi_rows else {},
        "dynamics": dynamics_rows,
        "status": status_rows,
        "tat": tat_rows,
    }


# ---------------------------------------------------------------------------
# Applications
# ---------------------------------------------------------------------------
async def get_applications_data(
    role: str, scope_id: UUID, filters: dict[str, Any], limit: int, offset: int
) -> dict[str, Any]:
    from_obj, has_dwh = _app_from_obj(filters)
    conditions = _app_conditions(role, scope_id, filters)

    kpi_stmt = (
        select(
            func.count().label("total"),
            func.countIf(f.c.lca_status == "under_review").label("new_cnt"),
            func.countIf(
                f.c.lca_status.in_(("approved_final", "approved_final_another_cond"))
            ).label("approved_cnt"),
            func.countIf(
                f.c.lca_status.in_(("rejected_prescoring", "rejected_approved", "closed"))
            ).label("rejected_cnt"),
            func.countIf(f.c.lca_status == "deal").label("issued_cnt"),
            func.avgIf(
                func.dateDiff("day", f.c.created_at, f.c.approved_at),
                and_(
                    f.c.lca_status.in_(("approved_final", "approved_final_another_cond")),
                    f.c.approved_at.is_not(None),
                ),
            ).label("avg_tat_days"),
        )
        .select_from(from_obj)
        .where(and_(*conditions))
    )
    if has_dwh:
        kpi_stmt = kpi_stmt.suffix_with("SETTINGS final = 1")

    total_expr = func.count().label("cnt")
    status_stmt = (
        select(
            f.c.lca_status.label("status"),
            total_expr,
            func.round(
                func.count()
                * 100.0
                / type_coerce(func.sum(func.count()).over(), Float),
                2,
            ).label("percentage"),
        )
        .select_from(from_obj)
        .where(and_(*conditions))
        .group_by(f.c.lca_status)
        .order_by(total_expr.desc())
    )
    if has_dwh:
        status_stmt = status_stmt.suffix_with("SETTINGS final = 1")

    day_expr = func.toDate(f.c.created_at).label("day")
    dynamics_stmt = (
        select(
            day_expr,
            func.count().label("total"),
            func.countIf(f.c.lca_status == "under_review").label("new_cnt"),
            func.countIf(
                f.c.lca_status.in_(("approved_final", "approved_final_another_cond"))
            ).label("approved_cnt"),
            func.countIf(f.c.lca_status == "deal").label("issued_cnt"),
        )
        .select_from(from_obj)
        .where(and_(*conditions))
        .group_by(day_expr)
        .order_by(day_expr)
    )
    if has_dwh:
        dynamics_stmt = dynamics_stmt.suffix_with("SETTINGS final = 1")

    table_stmt = (
        select(
            f.c.display_number.label("display_number"),
            f.c.dealer_company_id.label("dealer_company_id"),
            f.c.vehicle_mark_id.label("mark_id"),
            f.c.vehicle_model_id.label("model_id"),
            f.c.lca_status.label("status"),
            f.c.total_amount.label("total_amount"),
            f.c.down_payment.label("down_payment"),
            f.c.lease_term_months.label("lease_term_months"),
            f.c.monthly_payment.label("monthly_payment"),
            f.c.rate.label("rate"),
            f.c.created_at.label("created_at"),
            f.c.approved_at.label("approved_at"),
        )
        .select_from(from_obj)
        .where(and_(*conditions))
        .order_by(f.c.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    if has_dwh:
        table_stmt = table_stmt.suffix_with("SETTINGS final = 1")

    count_stmt = (
        select(func.count().label("total"))
        .select_from(from_obj)
        .where(and_(*conditions))
    )
    if has_dwh:
        count_stmt = count_stmt.suffix_with("SETTINGS final = 1")

    kpi_rows = await _execute(kpi_stmt)
    status_rows = await _execute(status_stmt)
    dynamics_rows = await _execute(dynamics_stmt)
    table_rows = await _execute(table_stmt)
    count_rows = await _execute(count_stmt)

    return {
        "kpi": kpi_rows[0] if kpi_rows else {},
        "status": status_rows,
        "dynamics": dynamics_rows,
        "table": [
            {
                "display_number": row.get("display_number"),
                "dealer_company_id": row.get("dealer_company_id"),
                "mark_id": row.get("mark_id"),
                "model_id": row.get("model_id"),
                "status": row.get("status"),
                "total_amount": _safe_float(row.get("total_amount")),
                "down_payment": _safe_float(row.get("down_payment")),
                "lease_term_months": _safe_int(row.get("lease_term_months")),
                "monthly_payment": _safe_float(row.get("monthly_payment")),
                "rate": _safe_float(row.get("rate")),
                "created_at": str(row.get("created_at")),
                "approved_at": str(row.get("approved_at")),
            }
            for row in table_rows
        ],
        "count": count_rows[0] if count_rows else {},
    }


# ---------------------------------------------------------------------------
# Proposals
# ---------------------------------------------------------------------------
async def get_proposals_data(
    role: str, scope_id: UUID, filters: dict[str, Any], limit: int, offset: int
) -> dict[str, Any]:
    from_obj, has_dwh = _proposal_from_obj(filters)
    conditions = _proposal_conditions(role, scope_id, filters)

    kpi_stmt = (
        select(
            func.count().label("total"),
            func.countIf(p.c.client_decision_action == "accepted").label(
                "accepted_cnt"
            ),
            func.countIf(p.c.client_decision_action == "rejected").label(
                "rejected_cnt"
            ),
            func.countIf(p.c.client_decision_action.is_(None)).label("pending_cnt"),
            func.avg(p.c.rate).label("avg_rate"),
            func.avg(p.c.lease_term_months).label("avg_term"),
        )
        .select_from(from_obj)
        .where(and_(*conditions))
    )
    if has_dwh:
        kpi_stmt = kpi_stmt.suffix_with("SETTINGS final = 1")

    total_expr = func.count().label("cnt")
    kind_stmt = (
        select(
            p.c.kind.label("kind"),
            total_expr,
            func.round(
                func.count()
                * 100.0
                / type_coerce(func.sum(func.count()).over(), Float),
                2,
            ).label("percentage"),
        )
        .select_from(from_obj)
        .where(and_(*conditions))
        .group_by(p.c.kind)
        .order_by(total_expr.desc())
    )
    if has_dwh:
        kind_stmt = kind_stmt.suffix_with("SETTINGS final = 1")

    day_expr = func.toDate(p.c.proposal_created_at).label("day")
    dynamics_stmt = (
        select(
            day_expr,
            func.count().label("total"),
            func.countIf(p.c.client_decision_action == "accepted").label(
                "accepted_cnt"
            ),
            func.countIf(p.c.client_decision_action == "rejected").label(
                "rejected_cnt"
            ),
        )
        .select_from(from_obj)
        .where(and_(*conditions))
        .group_by(day_expr)
        .order_by(day_expr)
    )
    if has_dwh:
        dynamics_stmt = dynamics_stmt.suffix_with("SETTINGS final = 1")

    table_stmt = (
        select(
            p.c.proposal_id.label("proposal_id"),
            p.c.application_id.label("application_id"),
            p.c.kind.label("kind"),
            p.c.total_amount.label("total_amount"),
            p.c.rate.label("rate"),
            p.c.lease_term_months.label("lease_term_months"),
            p.c.monthly_payment.label("monthly_payment"),
            p.c.client_decision_action.label("client_decision_action"),
            p.c.client_decision_comment.label("client_decision_comment"),
            p.c.proposal_created_at.label("proposal_created_at"),
        )
        .select_from(from_obj)
        .where(and_(*conditions))
        .order_by(p.c.proposal_created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    if has_dwh:
        table_stmt = table_stmt.suffix_with("SETTINGS final = 1")

    count_stmt = (
        select(func.count().label("total"))
        .select_from(from_obj)
        .where(and_(*conditions))
    )
    if has_dwh:
        count_stmt = count_stmt.suffix_with("SETTINGS final = 1")

    kpi_rows = await _execute(kpi_stmt)
    kind_rows = await _execute(kind_stmt)
    dynamics_rows = await _execute(dynamics_stmt)
    table_rows = await _execute(table_stmt)
    count_rows = await _execute(count_stmt)

    return {
        "kpi": kpi_rows[0] if kpi_rows else {},
        "kind": kind_rows,
        "dynamics": dynamics_rows,
        "table": [
            {
                "proposal_id": row.get("proposal_id"),
                "application_id": str(row.get("application_id")),
                "kind": row.get("kind"),
                "total_amount": _safe_float(row.get("total_amount")),
                "rate": _safe_float(row.get("rate")),
                "lease_term_months": _safe_int(row.get("lease_term_months")),
                "monthly_payment": _safe_float(row.get("monthly_payment")),
                "client_decision_action": row.get("client_decision_action"),
                "client_decision_comment": row.get("client_decision_comment"),
                "proposal_created_at": str(row.get("proposal_created_at")),
            }
            for row in table_rows
        ],
        "count": count_rows[0] if count_rows else {},
    }


# ---------------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------------
async def get_documents_data(
    role: str, scope_id: UUID, filters: dict[str, Any], limit: int, offset: int
) -> dict[str, Any]:
    from_obj, has_dwh = _doc_from_obj(role, filters)
    conditions = _doc_conditions(role, scope_id, filters)

    kpi_stmt = (
        select(
            func.count().label("total"),
            func.countIf(d.c.status == "approved").label("approved_cnt"),
            func.countIf(d.c.status == "pending_review").label("pending_cnt"),
            func.countIf(d.c.status == "rejected").label("rejected_cnt"),
        )
        .select_from(from_obj)
        .where(and_(*conditions))
    )
    if has_dwh:
        kpi_stmt = kpi_stmt.suffix_with("SETTINGS final = 1")

    total_expr = func.count().label("cnt")
    type_stmt = (
        select(
            d.c.document_type.label("document_type"),
            total_expr,
            func.round(
                func.count()
                * 100.0
                / type_coerce(func.sum(func.count()).over(), Float),
                2,
            ).label("percentage"),
        )
        .select_from(from_obj)
        .where(and_(*conditions))
        .group_by(d.c.document_type)
        .order_by(total_expr.desc())
    )
    if has_dwh:
        type_stmt = type_stmt.suffix_with("SETTINGS final = 1")

    day_expr = func.toDate(d.c.created_at).label("day")
    dynamics_stmt = (
        select(
            day_expr,
            func.count().label("total"),
            func.countIf(d.c.status == "approved").label("approved_cnt"),
            func.countIf(d.c.status == "pending_review").label("pending_cnt"),
            func.countIf(d.c.status == "rejected").label("rejected_cnt"),
        )
        .select_from(from_obj)
        .where(and_(*conditions))
        .group_by(day_expr)
        .order_by(day_expr)
    )
    if has_dwh:
        dynamics_stmt = dynamics_stmt.suffix_with("SETTINGS final = 1")

    table_stmt = (
        select(
            d.c.document_id.label("document_id"),
            d.c.document_type.label("document_type"),
            d.c.file_name.label("file_name"),
            d.c.status.label("status"),
            d.c.leasing_company_status.label("lc_status"),
            d.c.related_application_id.label("related_application_id"),
            d.c.verified_by.label("verified_by"),
            d.c.created_at.label("created_at"),
            d.c.updated_at.label("updated_at"),
        )
        .select_from(from_obj)
        .where(and_(*conditions))
        .order_by(d.c.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    if has_dwh:
        table_stmt = table_stmt.suffix_with("SETTINGS final = 1")

    count_stmt = (
        select(func.count().label("total"))
        .select_from(from_obj)
        .where(and_(*conditions))
    )
    if has_dwh:
        count_stmt = count_stmt.suffix_with("SETTINGS final = 1")

    kpi_rows = await _execute(kpi_stmt)
    type_rows = await _execute(type_stmt)
    dynamics_rows = await _execute(dynamics_stmt)
    table_rows = await _execute(table_stmt)
    count_rows = await _execute(count_stmt)

    return {
        "kpi": kpi_rows[0] if kpi_rows else {},
        "type": type_rows,
        "dynamics": dynamics_rows,
        "table": [
            {
                "document_id": row.get("document_id"),
                "document_type": row.get("document_type"),
                "file_name": row.get("file_name"),
                "status": row.get("status"),
                "lc_status": row.get("lc_status"),
                "related_application_id": str(row.get("related_application_id")),
                "verified_by": row.get("verified_by"),
                "created_at": str(row.get("created_at")),
                "updated_at": str(row.get("updated_at")),
            }
            for row in table_rows
        ],
        "count": count_rows[0] if count_rows else {},
    }


# ---------------------------------------------------------------------------
# Team
# ---------------------------------------------------------------------------
async def get_team_data(
    role: str, scope_id: UUID, filters: dict[str, Any], limit: int, offset: int
) -> dict[str, Any]:
    # Dealer team
    app_from_obj = f.join(
        dwh_lca,
        and_(
            dwh_lca.c.application_id == f.c.application_id,
            dwh_lca.c.leasing_company_id == f.c.leasing_company_id,
        ),
    ).join(u, u.c.company_id == dwh_lca.c.dealer_company_id)
    app_conditions = _app_conditions(role, scope_id, filters)

    total_apps_expr = func.count().label("total_apps")
    dealer_team_stmt = (
        select(
            u.c.user_id.label("employee_id"),
            u.c.name.label("employee_name"),
            total_apps_expr,
            func.countIf(
                f.c.lca_status.in_(("approved_final", "approved_final_another_cond"))
            ).label("approved_apps"),
            func.countIf(
                f.c.lca_status.in_(("rejected_prescoring", "rejected_approved", "closed"))
            ).label("rejected_apps"),
        )
        .select_from(app_from_obj)
        .where(and_(*app_conditions))
        .group_by(u.c.user_id, u.c.name)
        .order_by(total_apps_expr.desc())
        .limit(limit)
        .offset(offset)
        .suffix_with("SETTINGS final = 1")
    )

    dealer_count_stmt = (
        select(func.count(distinct(u.c.user_id)).label("total"))
        .select_from(app_from_obj)
        .where(and_(*app_conditions))
        .suffix_with("SETTINGS final = 1")
    )

    # LC team
    doc_from_obj, _ = _doc_from_obj(role, filters)
    doc_conditions = _doc_conditions(role, scope_id, filters)

    total_docs_expr = func.count().label("total_docs")
    lc_team_stmt = (
        select(
            d.c.verified_by.label("employee_id"),
            u.c.name.label("employee_name"),
            total_docs_expr,
            func.countIf(d.c.status == "approved").label("approved_docs"),
            func.countIf(d.c.status == "rejected").label("rejected_docs"),
        )
        .select_from(doc_from_obj.join(u, u.c.user_id == d.c.verified_by))
        .where(and_(*doc_conditions))
        .group_by(d.c.verified_by, u.c.name)
        .order_by(total_docs_expr.desc())
        .limit(limit)
        .offset(offset)
        .suffix_with("SETTINGS final = 1")
    )

    lc_count_stmt = (
        select(func.count(distinct(d.c.verified_by)).label("total"))
        .select_from(doc_from_obj)
        .where(and_(*doc_conditions))
        .suffix_with("SETTINGS final = 1")
    )

    dealer_rows = await _execute(dealer_team_stmt)
    dealer_count_rows = await _execute(dealer_count_stmt)
    lc_rows = await _execute(lc_team_stmt)
    lc_count_rows = await _execute(lc_count_stmt)

    return {
        "dealer_table": [
            {
                "employee_id": row.get("employee_id"),
                "employee_name": row.get("employee_name"),
                "total_apps": _safe_int(row.get("total_apps")),
                "approved_apps": _safe_int(row.get("approved_apps")),
                "rejected_apps": _safe_int(row.get("rejected_apps")),
            }
            for row in dealer_rows
        ],
        "dealer_count": dealer_count_rows[0] if dealer_count_rows else {},
        "lc_table": [
            {
                "employee_id": row.get("employee_id"),
                "employee_name": row.get("employee_name"),
                "total_docs": _safe_int(row.get("total_docs")),
                "approved_docs": _safe_int(row.get("approved_docs")),
                "rejected_docs": _safe_int(row.get("rejected_docs")),
            }
            for row in lc_rows
        ],
        "lc_count": lc_count_rows[0] if lc_count_rows else {},
    }


# ---------------------------------------------------------------------------
# Financials
# ---------------------------------------------------------------------------
async def get_financials_data(
    role: str, scope_id: UUID, filters: dict[str, Any], limit: int, offset: int
) -> dict[str, Any]:
    from_obj, has_dwh = _app_from_obj(filters)
    conditions = _app_conditions(role, scope_id, filters)

    kpi_stmt = (
        select(
            func.sumIf(f.c.total_amount, f.c.lca_status == "under_review").label(
                "pipeline"
            ),
            func.sumIf(
                f.c.total_amount, f.c.lca_status.in_(("approved_final", "approved_final_another_cond"))
            ).label("approved_volume"),
            func.sumIf(f.c.total_amount, f.c.lca_status == "deal").label(
                "issued_volume"
            ),
            func.avgIf(
                f.c.rate, f.c.lca_status.in_(("approved_final", "approved_final_another_cond"))
            ).label("avg_rate"),
            func.avgIf(
                f.c.lease_term_months, f.c.lca_status.in_(("approved_final", "approved_final_another_cond"))
            ).label("avg_term"),
            func.avgIf(
                f.c.down_payment_percent, f.c.lca_status.in_(("approved_final", "approved_final_another_cond"))
            ).label("avg_down_pct"),
        )
        .select_from(from_obj)
        .where(and_(*conditions))
    )
    if has_dwh:
        kpi_stmt = kpi_stmt.suffix_with("SETTINGS final = 1")

    amount_expr = func.sum(f.c.total_amount).label("amount")
    cnt_expr = func.count().label("cnt")
    funnel_stmt = (
        select(
            f.c.lca_status.label("status"),
            amount_expr,
            cnt_expr,
        )
        .select_from(from_obj)
        .where(and_(*conditions))
        .group_by(f.c.lca_status)
        .order_by(amount_expr.desc())
    )
    if has_dwh:
        funnel_stmt = funnel_stmt.suffix_with("SETTINGS final = 1")

    day_expr = func.toDate(f.c.created_at).label("day")
    dynamics_stmt = (
        select(
            day_expr,
            func.sumIf(
                f.c.total_amount, f.c.lca_status.in_(("approved_final", "approved_final_another_cond"))
            ).label("approved_amount"),
            func.sumIf(f.c.total_amount, f.c.lca_status == "deal").label(
                "issued_amount"
            ),
            func.sumIf(f.c.total_amount, f.c.lca_status == "under_review").label(
                "pipeline_amount"
            ),
        )
        .select_from(from_obj)
        .where(and_(*conditions))
        .group_by(day_expr)
        .order_by(day_expr)
    )
    if has_dwh:
        dynamics_stmt = dynamics_stmt.suffix_with("SETTINGS final = 1")

    table_stmt = (
        select(
            f.c.display_number.label("display_number"),
            f.c.lca_status.label("status"),
            f.c.total_amount.label("total_amount"),
            f.c.down_payment.label("down_payment"),
            f.c.down_payment_percent.label("down_payment_percent"),
            f.c.lease_term_months.label("lease_term_months"),
            f.c.monthly_payment.label("monthly_payment"),
            f.c.rate.label("rate"),
            f.c.markup.label("markup"),
            f.c.total_cost.label("total_cost"),
            f.c.created_at.label("created_at"),
        )
        .select_from(from_obj)
        .where(and_(*conditions))
        .order_by(f.c.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    if has_dwh:
        table_stmt = table_stmt.suffix_with("SETTINGS final = 1")

    count_stmt = (
        select(func.count().label("total"))
        .select_from(from_obj)
        .where(and_(*conditions))
    )
    if has_dwh:
        count_stmt = count_stmt.suffix_with("SETTINGS final = 1")

    kpi_rows = await _execute(kpi_stmt)
    funnel_rows = await _execute(funnel_stmt)
    dynamics_rows = await _execute(dynamics_stmt)
    table_rows = await _execute(table_stmt)
    count_rows = await _execute(count_stmt)

    return {
        "kpi": kpi_rows[0] if kpi_rows else {},
        "funnel": funnel_rows,
        "dynamics": dynamics_rows,
        "table": [
            {
                "display_number": row.get("display_number"),
                "status": row.get("status"),
                "total_amount": _safe_float(row.get("total_amount")),
                "down_payment": _safe_float(row.get("down_payment")),
                "down_payment_percent": _safe_float(row.get("down_payment_percent")),
                "lease_term_months": _safe_int(row.get("lease_term_months")),
                "monthly_payment": _safe_float(row.get("monthly_payment")),
                "rate": _safe_float(row.get("rate")),
                "markup": _safe_float(row.get("markup")),
                "total_cost": _safe_float(row.get("total_cost")),
                "created_at": str(row.get("created_at")),
            }
            for row in table_rows
        ],
        "count": count_rows[0] if count_rows else {},
    }


# ---------------------------------------------------------------------------
# Exchange
# ---------------------------------------------------------------------------
async def get_exchange_data(
    role: str, scope_id: UUID, filters: dict[str, Any], limit: int, offset: int
) -> dict[str, Any]:
    from_obj, has_dwh = _exchange_from_obj(role, filters)
    conditions = _exchange_conditions(role, scope_id, filters)

    bid_stats_full = (
        select(
            eb.c.request_id,
            func.count().label("total_bids"),
            func.countIf(eb.c.is_accepted == 1).label("accepted_bids"),
            func.avg(eb.c.price).label("avg_price"),
        )
        .group_by(eb.c.request_id)
        .suffix_with("SETTINGS final = 1")
        .subquery()
    )

    bid_stats_simple = (
        select(
            eb.c.request_id,
            func.count().label("total_bids"),
        )
        .group_by(eb.c.request_id)
        .suffix_with("SETTINGS final = 1")
        .subquery()
    )

    kpi_stmt = (
        select(
            func.count().label("total_requests"),
            func.countIf(er.c.status == "active").label("active_requests"),
            func.sum(bid_stats_full.c.total_bids).label("total_bids"),
            func.sum(bid_stats_full.c.accepted_bids).label("accepted_bids"),
            func.avg(bid_stats_full.c.avg_price).label("avg_price"),
        )
        .select_from(
            from_obj.join(
                bid_stats_full,
                bid_stats_full.c.request_id == er.c.request_id,
                isouter=True,
            )
        )
        .where(and_(*conditions))
    )
    if has_dwh:
        kpi_stmt = kpi_stmt.suffix_with("SETTINGS final = 1")

    total_expr = func.count().label("cnt")
    status_stmt = (
        select(
            er.c.status.label("status"),
            total_expr,
            func.round(
                func.count()
                * 100.0
                / type_coerce(func.sum(func.count()).over(), Float),
                2,
            ).label("percentage"),
        )
        .select_from(from_obj)
        .where(and_(*conditions))
        .group_by(er.c.status)
        .order_by(total_expr.desc())
    )
    if has_dwh:
        status_stmt = status_stmt.suffix_with("SETTINGS final = 1")

    day_expr = func.toDate(er.c.created_at).label("day")
    dynamics_stmt = (
        select(
            day_expr,
            func.count().label("requests"),
            func.sum(bid_stats_simple.c.total_bids).label("bids"),
        )
        .select_from(
            from_obj.join(
                bid_stats_simple,
                bid_stats_simple.c.request_id == er.c.request_id,
                isouter=True,
            )
        )
        .where(and_(*conditions))
        .group_by(day_expr)
        .order_by(day_expr)
    )
    if has_dwh:
        dynamics_stmt = dynamics_stmt.suffix_with("SETTINGS final = 1")

    table_stmt = (
        select(
            er.c.request_id.label("request_id"),
            er.c.status.label("status"),
            er.c.quantity.label("quantity"),
            er.c.discount_type.label("discount_type"),
            er.c.discount_value.label("discount_value"),
            er.c.created_at.label("created_at"),
            bid_stats_full.c.total_bids.label("total_bids"),
            bid_stats_full.c.accepted_bids.label("accepted_bids"),
            bid_stats_full.c.avg_price.label("avg_price"),
        )
        .select_from(
            from_obj.join(
                bid_stats_full,
                bid_stats_full.c.request_id == er.c.request_id,
                isouter=True,
            )
        )
        .where(and_(*conditions))
        .order_by(er.c.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    if has_dwh:
        table_stmt = table_stmt.suffix_with("SETTINGS final = 1")

    count_stmt = (
        select(func.count().label("total"))
        .select_from(from_obj)
        .where(and_(*conditions))
    )
    if has_dwh:
        count_stmt = count_stmt.suffix_with("SETTINGS final = 1")

    kpi_rows = await _execute(kpi_stmt)
    status_rows = await _execute(status_stmt)
    dynamics_rows = await _execute(dynamics_stmt)
    table_rows = await _execute(table_stmt)
    count_rows = await _execute(count_stmt)

    return {
        "kpi": kpi_rows[0] if kpi_rows else {},
        "status": status_rows,
        "dynamics": dynamics_rows,
        "table": [
            {
                "request_id": row.get("request_id"),
                "status": row.get("status"),
                "quantity": _safe_int(row.get("quantity")),
                "discount_type": row.get("discount_type"),
                "discount_value": _safe_float(row.get("discount_value")),
                "created_at": str(row.get("created_at")),
                "total_bids": _safe_int(row.get("total_bids")),
                "accepted_bids": _safe_int(row.get("accepted_bids")),
                "avg_price": _safe_float(row.get("avg_price")),
            }
            for row in table_rows
        ],
        "count": count_rows[0] if count_rows else {},
    }
