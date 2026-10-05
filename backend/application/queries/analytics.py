"""Analytics query handlers — assemble repository data into dashboard widgets.

Light transformation only: status labels, chart series, safe numeric
conversions.  No SQL here.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from infrastructure.repositories import analytics_repository as repo

_STATUS_COLORS = {
    "submitted": "#90A4AE",
    "under_review": "#4DA2F1",
    "approved_scoring": "#8CD5FF",
    "approved_scoring_another_cond": "#4DB6AC",
    "rejected_prescoring": "#FF8A80",
    "documents_required": "#FFB433",
    "under_review_with_docs": "#FFCC80",
    "approved_final": "#2E7D32",
    "approved_final_another_cond": "#66BB6A",
    "rejected_approved": "#FF3D64",
    "selected_lc": "#BA68C8",
    "deal": "#1E69A9",
    "closed": "#AB94D9",
}

_STATUS_LABELS = {
    "submitted": "Подана",
    "under_review": "На рассмотрении",
    "approved_scoring": "Одобрено на скоринге",
    "approved_scoring_another_cond": "Одобрено на других условиях",
    "rejected_prescoring": "Отказано на скоринге",
    "documents_required": "Требуются доп доки",
    "under_review_with_docs": "На рассмотрении с доп. документами",
    "approved_final": "Одобрение итоговое",
    "approved_final_another_cond": "Одобрение итоговое на других условиях",
    "rejected_approved": "Отказано после рассмотрения",
    "selected_lc": "Выбрана ЛК",
    "deal": "Профинансировано",
    "closed": "Закрыта клиентом",
}


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


# ---------------------------------------------------------------------------
# Overview
# ---------------------------------------------------------------------------
async def get_overview_widgets(
    role: str, scope_id: UUID, filters: dict[str, Any]
) -> dict[str, Any]:
    data = await repo.get_overview_data(role, scope_id, filters)
    kpi = data.get("kpi") or {}

    new_apps = _safe_int(kpi.get("new_cnt"))
    in_review = _safe_int(kpi.get("in_review_cnt"))
    approved = _safe_int(kpi.get("approved_cnt"))
    issued = _safe_int(kpi.get("issued_cnt"))
    rejected = _safe_int(kpi.get("rejected_cnt"))
    approved_volume = _safe_float(kpi.get("approved_volume"))
    issued_volume = _safe_float(kpi.get("issued_volume"))

    new_series = []
    approved_series = []
    issued_series = []
    for row in data.get("dynamics") or []:
        day = _format_day(row.get("day"))
        new_series.append({"x": day, "y": _safe_int(row.get("new_cnt"))})
        approved_series.append({"x": day, "y": _safe_int(row.get("approved_cnt"))})
        issued_series.append({"x": day, "y": _safe_int(row.get("issued_cnt"))})

    status_labels = []
    status_counts = []
    status_colors = []
    donut_slices = []
    for row in data.get("status") or []:
        st = row.get("status")
        cnt = _safe_int(row.get("cnt"))
        label = _STATUS_LABELS.get(st, st)
        color = _STATUS_COLORS.get(st, "#9E9E9E")
        status_labels.append(label)
        status_counts.append(cnt)
        status_colors.append(color)
        donut_slices.append({"label": label, "value": cnt, "color": color})

    tat_labels = []
    tat_values = []
    tat_colors = []
    for row in data.get("tat") or []:
        st = row.get("status")
        label = _STATUS_LABELS.get(st, st)
        color = _STATUS_COLORS.get(st, "#9E9E9E")
        tat_labels.append(label)
        tat_values.append(_safe_float(row.get("avg_tat")))
        tat_colors.append(color)

    return {
        "W-OVR-01": {"value": new_apps},
        "W-OVR-02": {"value": in_review},
        "W-OVR-03": {"value": approved},
        "W-OVR-04": {"value": issued},
        "W-OVR-05": {"value": rejected},
        "W-OVR-06": {"value": approved_volume},
        "W-OVR-07": {"value": issued_volume},
        "W-OVR-08": {"value": round(approved_volume / approved, 2) if approved else 0},
        "W-OVR-09": [
            {
                "name": "Кол-во новые",
                "color": "#4DA2F1",
                "data": new_series,
            },
            {
                "name": "Кол-во одобрено",
                "color": "#2E7D32",
                "data": approved_series,
            },
            {
                "name": "Кол-во профинансировано",
                "color": "#FF3D64",
                "data": issued_series,
                "dashed": True,
            },
        ],
        "W-OVR-10": donut_slices,
        "W-OVR-11": {
            "labels": status_labels,
            "datasets": [
                {"name": "Количество", "color": "#4DA2F1", "data": status_counts}
            ],
        },
        "W-OVR-12": {
            "labels": tat_labels,
            "datasets": [
                {"name": "ТАТ (дней)", "color": "#DB9101", "data": tat_values}
            ],
        },
    }


# ---------------------------------------------------------------------------
# Applications
# ---------------------------------------------------------------------------
async def get_applications_widgets(
    role: str, scope_id: UUID, filters: dict[str, Any], limit: int, offset: int
) -> dict[str, Any]:
    data = await repo.get_applications_data(role, scope_id, filters, limit, offset)
    kpi = data.get("kpi") or {}
    total = _safe_int(kpi.get("total"))

    new_series = []
    approved_series = []
    issued_series = []
    for row in data.get("dynamics") or []:
        day = _format_day(row.get("day"))
        new_series.append({"x": day, "y": _safe_int(row.get("new_cnt"))})
        approved_series.append({"x": day, "y": _safe_int(row.get("approved_cnt"))})
        issued_series.append({"x": day, "y": _safe_int(row.get("issued_cnt"))})

    status_rows = data.get("status") or []
    count_row = data.get("count") or {}

    return {
        "W-APP-01": {"value": total},
        "W-APP-02": {"value": _safe_int(kpi.get("new_cnt"))},
        "W-APP-03": {"value": _safe_int(kpi.get("approved_cnt"))},
        "W-APP-04": {"value": _safe_int(kpi.get("rejected_cnt"))},
        "W-APP-05": {"value": round(_safe_float(kpi.get("avg_tat_days")), 1)},
        "W-APP-06": {
            "labels": [_STATUS_LABELS.get(r["status"], r["status"]) for r in status_rows],
            "datasets": [
                {
                    "name": "Количество",
                    "color": "#4DA2F1",
                    "data": [_safe_int(r["cnt"]) for r in status_rows],
                }
            ],
        },
        "W-APP-07": [
            {"name": "Новые", "color": "#0077CC", "data": new_series},
            {"name": "Одобрены", "color": "#2E7D32", "data": approved_series},
            {"name": "Выданы", "color": "#9E9E9E", "data": issued_series},
        ],
        "W-APP-08": {
            "items": data.get("table") or [],
            "pagination": {
                "total": _safe_int(count_row.get("total")),
                "limit": limit,
                "offset": offset,
            },
        },
    }


# ---------------------------------------------------------------------------
# Proposals
# ---------------------------------------------------------------------------
async def get_proposals_widgets(
    role: str, scope_id: UUID, filters: dict[str, Any], limit: int, offset: int
) -> dict[str, Any]:
    data = await repo.get_proposals_data(role, scope_id, filters, limit, offset)
    kpi = data.get("kpi") or {}
    count_row = data.get("count") or {}

    total_series = []
    accepted_series = []
    rejected_series = []
    for row in data.get("dynamics") or []:
        day = _format_day(row.get("day"))
        total_series.append({"x": day, "y": _safe_int(row.get("total"))})
        accepted_series.append({"x": day, "y": _safe_int(row.get("accepted_cnt"))})
        rejected_series.append({"x": day, "y": _safe_int(row.get("rejected_cnt"))})

    return {
        "W-PRP-01": {"value": _safe_int(kpi.get("total"))},
        "W-PRP-02": {"value": _safe_int(kpi.get("accepted_cnt"))},
        "W-PRP-03": {"value": _safe_int(kpi.get("rejected_cnt"))},
        "W-PRP-04": {"value": _safe_int(kpi.get("pending_cnt"))},
        "W-PRP-05": {"value": round(_safe_float(kpi.get("avg_rate")), 2)},
        "W-PRP-06": {"value": round(_safe_float(kpi.get("avg_term")), 1)},
        "W-PRP-07": [
            {
                "kind": r["kind"],
                "count": _safe_int(r["cnt"]),
                "percentage": _safe_float(r["percentage"]),
            }
            for r in data.get("kind") or []
        ],
        "W-PRP-08": [
            {"name": "Всего", "color": "#0077CC", "data": total_series},
            {"name": "Принято", "color": "#2E7D32", "data": accepted_series},
            {"name": "Отклонено", "color": "#E54D4D", "data": rejected_series},
        ],
        "W-PRP-09": {
            "items": data.get("table") or [],
            "pagination": {
                "total": _safe_int(count_row.get("total")),
                "limit": limit,
                "offset": offset,
            },
        },
    }


# ---------------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------------
async def get_documents_widgets(
    role: str, scope_id: UUID, filters: dict[str, Any], limit: int, offset: int
) -> dict[str, Any]:
    data = await repo.get_documents_data(role, scope_id, filters, limit, offset)
    kpi = data.get("kpi") or {}
    count_row = data.get("count") or {}

    total_series = []
    approved_series = []
    pending_series = []
    rejected_series = []
    for row in data.get("dynamics") or []:
        day = _format_day(row.get("day"))
        total_series.append({"x": day, "y": _safe_int(row.get("total"))})
        approved_series.append({"x": day, "y": _safe_int(row.get("approved_cnt"))})
        pending_series.append({"x": day, "y": _safe_int(row.get("pending_cnt"))})
        rejected_series.append({"x": day, "y": _safe_int(row.get("rejected_cnt"))})

    return {
        "W-DOC-01": {"value": _safe_int(kpi.get("total"))},
        "W-DOC-02": {"value": _safe_int(kpi.get("approved_cnt"))},
        "W-DOC-03": {"value": _safe_int(kpi.get("pending_cnt"))},
        "W-DOC-04": {"value": _safe_int(kpi.get("rejected_cnt"))},
        "W-DOC-05": [
            {
                "type": r["document_type"],
                "count": _safe_int(r["cnt"]),
                "percentage": _safe_float(r["percentage"]),
            }
            for r in data.get("type") or []
        ],
        "W-DOC-06": [
            {"name": "Всего", "color": "#0077CC", "data": total_series},
            {"name": "Одобрено", "color": "#2E7D32", "data": approved_series},
            {"name": "На проверке", "color": "#F5A623", "data": pending_series},
            {"name": "Отклонено", "color": "#E54D4D", "data": rejected_series},
        ],
        "W-DOC-07": {
            "items": data.get("table") or [],
            "pagination": {
                "total": _safe_int(count_row.get("total")),
                "limit": limit,
                "offset": offset,
            },
        },
    }


# ---------------------------------------------------------------------------
# Team
# ---------------------------------------------------------------------------
async def get_team_widgets(
    role: str, scope_id: UUID, filters: dict[str, Any], limit: int, offset: int
) -> dict[str, Any]:
    data = await repo.get_team_data(role, scope_id, filters, limit, offset)
    dealer_items = data.get("dealer_table") or []
    lc_items = data.get("lc_table") or []
    dealer_count = data.get("dealer_count") or {}
    lc_count = data.get("lc_count") or {}

    total_dealer_employees = _safe_int(dealer_count.get("total"))
    total_lc_reviewers = _safe_int(lc_count.get("total"))
    total_apps = sum(_safe_int(r["total_apps"]) for r in dealer_items)
    total_docs = sum(_safe_int(r["total_docs"]) for r in lc_items)

    return {
        "W-TEA-01": {"value": total_dealer_employees},
        "W-TEA-02": {"value": total_lc_reviewers},
        "W-TEA-03": {
            "value": round(total_apps / total_dealer_employees, 1)
            if total_dealer_employees
            else 0
        },
        "W-TEA-04": {
            "value": round(total_docs / total_lc_reviewers, 1)
            if total_lc_reviewers
            else 0
        },
        "W-TEA-05": {
            "items": dealer_items,
            "pagination": {
                "total": total_dealer_employees,
                "limit": limit,
                "offset": offset,
            },
        },
        "W-TEA-06": {
            "items": lc_items,
            "pagination": {
                "total": total_lc_reviewers,
                "limit": limit,
                "offset": offset,
            },
        },
    }


# ---------------------------------------------------------------------------
# Financials
# ---------------------------------------------------------------------------
async def get_financials_widgets(
    role: str, scope_id: UUID, filters: dict[str, Any], limit: int, offset: int
) -> dict[str, Any]:
    data = await repo.get_financials_data(role, scope_id, filters, limit, offset)
    kpi = data.get("kpi") or {}
    count_row = data.get("count") or {}

    approved_series = []
    issued_series = []
    pipeline_series = []
    for row in data.get("dynamics") or []:
        day = _format_day(row.get("day"))
        approved_series.append({"x": day, "y": _safe_float(row.get("approved_amount"))})
        issued_series.append({"x": day, "y": _safe_float(row.get("issued_amount"))})
        pipeline_series.append({"x": day, "y": _safe_float(row.get("pipeline_amount"))})

    return {
        "W-FIN-01": {"value": _safe_float(kpi.get("pipeline"))},
        "W-FIN-02": {"value": _safe_float(kpi.get("approved_volume"))},
        "W-FIN-03": {"value": _safe_float(kpi.get("issued_volume"))},
        "W-FIN-04": {"value": round(_safe_float(kpi.get("avg_rate")), 2)},
        "W-FIN-05": {"value": round(_safe_float(kpi.get("avg_term")), 1)},
        "W-FIN-06": {"value": round(_safe_float(kpi.get("avg_down_pct")), 2)},
        "W-FIN-07": [
            {
                "status": r["status"],
                "amount": _safe_float(r["amount"]),
                "count": _safe_int(r["cnt"]),
            }
            for r in data.get("funnel") or []
        ],
        "W-FIN-08": [
            {"name": "Одобрено", "color": "#2E7D32", "data": approved_series},
            {"name": "Выдано", "color": "#9E9E9E", "data": issued_series},
            {"name": "В работе", "color": "#0077CC", "data": pipeline_series},
        ],
        "W-FIN-09": {
            "items": data.get("table") or [],
            "pagination": {
                "total": _safe_int(count_row.get("total")),
                "limit": limit,
                "offset": offset,
            },
        },
    }


# ---------------------------------------------------------------------------
# Exchange
# ---------------------------------------------------------------------------
async def get_exchange_widgets(
    role: str, scope_id: UUID, filters: dict[str, Any], limit: int, offset: int
) -> dict[str, Any]:
    data = await repo.get_exchange_data(role, scope_id, filters, limit, offset)
    kpi = data.get("kpi") or {}
    count_row = data.get("count") or {}

    requests_series = []
    bids_series = []
    for row in data.get("dynamics") or []:
        day = _format_day(row.get("day"))
        requests_series.append({"x": day, "y": _safe_int(row.get("requests"))})
        bids_series.append({"x": day, "y": _safe_int(row.get("bids"))})

    return {
        "W-EXC-01": {"value": _safe_int(kpi.get("total_requests"))},
        "W-EXC-02": {"value": _safe_int(kpi.get("active_requests"))},
        "W-EXC-03": {"value": _safe_int(kpi.get("total_bids"))},
        "W-EXC-04": {"value": _safe_int(kpi.get("accepted_bids"))},
        "W-EXC-05": {"value": round(_safe_float(kpi.get("avg_price")), 2)},
        "W-EXC-06": [
            {
                "status": r["status"],
                "count": _safe_int(r["cnt"]),
                "percentage": _safe_float(r["percentage"]),
            }
            for r in data.get("status") or []
        ],
        "W-EXC-07": [
            {"name": "Запросы", "color": "#0077CC", "data": requests_series},
            {"name": "Предложения", "color": "#2E7D32", "data": bids_series},
        ],
        "W-EXC-08": {
            "items": data.get("table") or [],
            "pagination": {
                "total": _safe_int(count_row.get("total")),
                "limit": limit,
                "offset": offset,
            },
        },
    }
