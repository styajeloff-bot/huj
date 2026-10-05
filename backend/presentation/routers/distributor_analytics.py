"""Distributor analytics dashboard router.

Mounts under ``/api/v1/distributor/analytics`` from main.py.
Requires the ``distributor`` role; RLS enforces company_id scope.
All endpoints are read-only against ClickHouse DWH.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Annotated, Any, cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from application.distributor_scope import resolve_distributor_scope
from application.permissions import get_company_permissions
from infrastructure.clickhouse_readonly import (
    _WAREHOUSE_STATUS_LABELS,
    _safe_float,
    _safe_int,
    clamp_discount_value,
    discount_label,
    exchange_status_label,
    get_distributor_applications_kpi,
    get_distributor_applications_status_stats,
    get_distributor_applications_table,
    get_distributor_applications_timeline,
    get_distributor_deals_timeline,
    get_distributor_exchange_kpi,
    get_distributor_exchange_table,
    get_distributor_exchange_timeline,
    get_distributor_financials_kpi,
    get_distributor_financials_table,
    get_distributor_financials_timeline,
    get_distributor_sales_dc,
    get_distributor_sales_dc_regions,
    get_distributor_warehouse_city_table,
    get_distributor_warehouse_dealer_table,
    get_distributor_warehouse_kpi,
    get_distributor_warehouse_mark_model_bar,
    get_distributor_warehouse_status_donut,
    get_distributor_warehouse_timeline,
    lca_status_label,
    model_display_label,
)
from infrastructure.database import get_db
from presentation.dependencies.auth import require_roles
from presentation.schemas.distributor_analytics import (
    BarChartData,
    BarChartSeries,
    ComboChartData,
    DistributorAnalyticsFilters,
    DistributorAnalyticsResponse,
    KpiWidget,
    LineChartSeries,
    PaginatedTable,
    Pagination,
    TimeSeriesPoint,
)

logger = logging.getLogger("carcraft-backend")

router = APIRouter()
SUPPORTED_ROLES = ("distributor", "carcraft_employee")
APPLICATIONS_SUPPORTED_ROLES = (*SUPPORTED_ROLES, "dealer")

_STATUS_COLORS: dict[str, str] = {
    "available": "#4CAF50",
    "reserved": "#FF9800",
    "sold": "#2196F3",
    "in_transit": "#9C27B0",
    "unknown": "#90A4AE",
}


def _get_scope_id(user: dict[str, Any]) -> UUID:
    role = str(user.get("role", ""))
    if role == "carcraft_employee":
        return cast("UUID", None)
    if role == "distributor":
        company_id = user.get("company_id")
        if company_id is None:
            raise HTTPException(
                status_code=403,
                detail={"error": "Пользователь не привязан к компании"},
            )
        scope_id = _coerce_uuid(company_id)
        if scope_id is None:
            raise HTTPException(
                status_code=403,
                detail={"error": "Некорректный идентификатор компании"},
            )
        return scope_id
    raise HTTPException(
        status_code=403,
        detail={"error": "Роль не поддерживается для аналитики"},
    )


def _coerce_uuid(value: Any) -> UUID | None:
    if isinstance(value, UUID):
        return value
    if isinstance(value, str) and value:
        try:
            return UUID(value)
        except ValueError:
            return None
    return None


def _get_applications_scope_id(user: dict[str, Any]) -> UUID:
    """Return the legacy analytics scope id for the applications tab."""
    if str(user.get("role", "")) == "dealer":
        company_id = _coerce_uuid(user.get("company_id"))
        if company_id is None:
            raise HTTPException(
                status_code=403,
                detail={"error": "Пользователь не привязан к компании"},
            )
        return company_id
    return _get_scope_id(user)


async def _resolve_scope_dealer_ids(
    user: dict[str, Any], session: AsyncSession
) -> list[UUID] | None:
    """Resolve the distributor dealer-scope filter for the current user.

    Returns ``None`` for ``carcraft_employee`` (no filter — sees all), the
    exact company for a permitted ``dealer``, or linked dealer company ids for
    a ``distributor`` (an empty list scopes that distributor to zero rows).
    """
    actor_id = _coerce_uuid(user.get("id"))
    if actor_id is None:
        raise HTTPException(
            status_code=403, detail={"error": "Не удалось определить пользователя"}
        )
    role = str(user.get("role", ""))
    company_id = _coerce_uuid(user.get("company_id"))
    if role == "dealer":
        if company_id is None:
            raise HTTPException(
                status_code=403,
                detail={"error": "Пользователь не привязан к компании"},
            )
        permissions = await get_company_permissions(session, actor_id, company_id)
        if not permissions.get("can_view_applications"):
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "Просмотр заявок ограничен администратором компании",
                    "code": "INSUFFICIENT_PERMISSIONS",
                },
            )
        return [company_id]

    scope = await resolve_distributor_scope(
        session,
        actor_id=actor_id,
        actor_role=role,
        company_id=company_id,
    )
    return cast("list[UUID] | None", scope.dealer_filter())


def _filters_from_query(
    period_from: date | None,
    period_to: date | None,
    cities: list[str] | None,
    marks: list[str] | None,
    models: list[str] | None,
    dealers: list[UUID] | None,
    statuses: list[str] | None,
) -> DistributorAnalyticsFilters:
    return DistributorAnalyticsFilters(
        period_from=period_from,
        period_to=period_to,
        cities=cities,
        marks=marks,
        models=models,
        dealers=dealers,
        statuses=statuses,
    )


def _to_iso(value: Any) -> str:
    if hasattr(value, "isoformat"):
        return str(cast("datetime | date", value).isoformat())
    return str(value)


def _build_pagination(total: int, page: int, limit: int) -> Pagination:
    pages = max(1, (total + limit - 1) // limit) if total > 0 else 1
    return Pagination(total=total, page=page, limit=limit, pages=pages)


def _build_month_labels(rows: list[dict[str, Any]], key: str = "month") -> list[str]:
    seen: set[str] = set()
    labels: list[str] = []
    for row in rows:
        val = _to_iso(row.get(key, ""))
        if val not in seen:
            seen.add(val)
            labels.append(val)
    return labels


def _warehouse_dealer_item(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "dealer_name": row.get("dealer_name") or "—",
        "count": _safe_int(row.get("count", row.get("cnt"))),
        "value": _safe_float(row.get("value", row.get("total_value"))),
    }


def _warehouse_city_item(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "city": row.get("city") or "—",
        "count": _safe_int(row.get("count", row.get("cnt"))),
        "value": _safe_float(row.get("value", row.get("total_value"))),
    }


def _display_model_item(row: dict[str, Any]) -> dict[str, Any]:
    model = row.get("model")
    row["model_raw"] = model
    row["model"] = model_display_label(model)
    return row


# ---------------------------------------------------------------------------
# warehouse  —  GET /api/v1/distributor/analytics/warehouse
# ---------------------------------------------------------------------------
@router.get(
    "/warehouse",
    response_model=DistributorAnalyticsResponse,
    summary="[distributor] Складская аналитика",
    description=(
        "KPI-виджеты, donut по статусам, bar chart по маркам/моделям, "
        "помесячный таймлайн, таблицы дилеров и городов."
    ),
)
async def warehouse_analytics(
    user: Annotated[dict[str, Any], Depends(require_roles(*SUPPORTED_ROLES))],
    session: Annotated[AsyncSession, Depends(get_db)],
    period_from: date | None = Query(default=None),
    period_to: date | None = Query(default=None),
    cities: list[str] | None = Query(default=None),
    marks: list[str] | None = Query(default=None),
    models: list[str] | None = Query(default=None),
    dealers: list[UUID] | None = Query(default=None),
    statuses: list[str] | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
) -> JSONResponse:
    scope_id = _get_scope_id(user)
    scope_dealer_ids = await _resolve_scope_dealer_ids(user, session)
    filters = _filters_from_query(period_from, period_to, cities, marks, models, dealers, statuses)

    try:
        kpi = await get_distributor_warehouse_kpi(
            scope_id, period_from, period_to,
            cities=cities, marks=marks, models=models, dealers=dealers, statuses=statuses,
            scope_dealer_ids=scope_dealer_ids,
        )
        status_rows = await get_distributor_warehouse_status_donut(
            scope_id, period_from, period_to,
            cities=cities, marks=marks, models=models, dealers=dealers,
            scope_dealer_ids=scope_dealer_ids,
        )
        mark_model_rows = await get_distributor_warehouse_mark_model_bar(
            scope_id, period_from, period_to,
            cities=cities, marks=marks, models=models, dealers=dealers,
            scope_dealer_ids=scope_dealer_ids,
        )
        timeline_rows = await get_distributor_warehouse_timeline(
            scope_id, period_from, period_to,
            cities=cities, marks=marks, models=models, dealers=dealers,
            scope_dealer_ids=scope_dealer_ids,
        )
        dealer_rows, dealer_total = await get_distributor_warehouse_dealer_table(
            scope_id, period_from, period_to,
            cities=cities, marks=marks, models=models, dealers=dealers,
            page=page, limit=limit,
            scope_dealer_ids=scope_dealer_ids,
        )
        city_rows, city_total = await get_distributor_warehouse_city_table(
            scope_id, period_from, period_to,
            cities=cities, marks=marks, models=models, dealers=dealers,
            page=page, limit=limit,
            scope_dealer_ids=scope_dealer_ids,
        )
    except Exception as exc:
        logger.warning("distributor_warehouse_analytics_failed err=%s", exc)
        raise HTTPException(
            status_code=503, detail={"error": "Аналитика временно недоступна"}
        ) from exc

    widgets: dict[str, Any] = {}

    # W-WHS-01 .. W-WHS-07
    widgets["W-WHS-01"] = KpiWidget(value=_safe_int(kpi.get("total")))
    widgets["W-WHS-02"] = KpiWidget(value=_safe_int(kpi.get("available")))
    widgets["W-WHS-03"] = KpiWidget(value=_safe_int(kpi.get("reserved")))
    widgets["W-WHS-04"] = KpiWidget(value=_safe_int(kpi.get("sold")))
    widgets["W-WHS-05"] = KpiWidget(value=_safe_float(kpi.get("total_value")))
    widgets["W-WHS-06"] = KpiWidget(value=_safe_int(kpi.get("dealer_count")))
    widgets["W-WHS-07"] = KpiWidget(value=_safe_float(kpi.get("avg_price")))

    # W-WHS-08: donut by status — {code, label(рус.), value, color}.
    if status_rows:
        widgets["W-WHS-08"] = [
            {
                "code": (code := str(r.get("status") or "unknown")),
                "label": _WAREHOUSE_STATUS_LABELS.get(code, code),
                "value": _safe_int(r.get("cnt")),
                "color": _STATUS_COLORS.get(code, "#90A4AE"),
            }
            for r in status_rows
        ]

    # W-WHS-09: bar chart by mark/model
    if mark_model_rows:
        labels: list[str] = []
        counts: list[int | float] = []
        for r in mark_model_rows:
            labels.append(f"{r.get('mark', '')} {model_display_label(r.get('model'))}".strip())
            counts.append(_safe_int(r.get("cnt")))
        widgets["W-WHS-09"] = BarChartData(
            labels=labels,
            datasets=[BarChartSeries(name="Автомобили", color="#4DA2F1", data=counts)],
        )

    # W-WHS-10: timeline bar chart
    if timeline_rows:
        t_labels = _build_month_labels(timeline_rows)
        t_counts = []
        # align counts to labels
        idx = 0
        for lbl in t_labels:
            if idx < len(timeline_rows) and _to_iso(timeline_rows[idx].get("month")) == lbl:
                t_counts.append(_safe_int(timeline_rows[idx].get("cnt")))
                idx += 1
            else:
                t_counts.append(0)
        widgets["W-WHS-10"] = BarChartData(
            labels=t_labels,
            datasets=[BarChartSeries(name="Поступления", color="#4CAF50", data=t_counts)],
        )

    # W-WHS-11: dealer table
    widgets["W-WHS-11"] = PaginatedTable(
        items=[_warehouse_dealer_item(dict(r)) for r in dealer_rows],
        pagination=_build_pagination(dealer_total, page, limit),
    )

    # W-WHS-12: city table
    widgets["W-WHS-12"] = PaginatedTable(
        items=[_warehouse_city_item(dict(r)) for r in city_rows],
        pagination=_build_pagination(city_total, page, limit),
    )

    return JSONResponse(
        content=jsonable_encoder(
            DistributorAnalyticsResponse(
                tab="warehouse",
                filters_applied=filters,
                widgets=widgets,
            )
        )
    )


# ---------------------------------------------------------------------------
# applications  —  GET /api/v1/distributor/analytics/applications
# ---------------------------------------------------------------------------
@router.get(
    "/applications",
    response_model=DistributorAnalyticsResponse,
    summary="[distributor, dealer, carcraft_employee] Аналитика по заявкам",
    description=(
        "KPI по заявкам, комбо-чарты заявок и сделок, таблица заявок. "
        "Для дилера доступ проверяется по актуальному разрешению "
        "can_view_applications и ограничивается собственной компанией."
    ),
)
async def applications_analytics(
    user: Annotated[
        dict[str, Any], Depends(require_roles(*APPLICATIONS_SUPPORTED_ROLES))
    ],
    session: Annotated[AsyncSession, Depends(get_db)],
    period_from: date | None = Query(default=None),
    period_to: date | None = Query(default=None),
    statuses: list[str] | None = Query(default=None),
    cities: list[str] | None = Query(default=None),
    marks: list[str] | None = Query(default=None),
    models: list[str] | None = Query(default=None),
    dealers: list[UUID] | None = Query(default=None),
    leasing_companies: list[str] | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
) -> JSONResponse:
    scope_id = _get_applications_scope_id(user)
    scope_dealer_ids = await _resolve_scope_dealer_ids(user, session)
    filters = _filters_from_query(period_from, period_to, cities, marks, models, dealers, statuses)
    common: dict[str, Any] = {
        "cities": cities, "marks": marks, "models": models, "dealers": dealers,
        "leasing_companies": leasing_companies, "scope_dealer_ids": scope_dealer_ids,
    }

    try:
        kpi = await get_distributor_applications_kpi(
            scope_id, period_from, period_to, statuses=statuses, **common,
        )
        status_stats = await get_distributor_applications_status_stats(
            scope_id, period_from, period_to, statuses=statuses, **common,
        )
        app_timeline = await get_distributor_applications_timeline(
            scope_id, period_from, period_to, statuses=statuses, **common,
        )
        deal_timeline = await get_distributor_deals_timeline(
            scope_id, period_from, period_to, statuses=statuses, **common,
        )
        table_rows, total = await get_distributor_applications_table(
            scope_id, period_from, period_to, statuses=statuses,
            page=page, limit=limit, **common,
        )
    except Exception as exc:
        logger.warning("distributor_applications_analytics_failed err=%s", exc)
        raise HTTPException(
            status_code=503, detail={"error": "Аналитика временно недоступна"}
        ) from exc

    widgets: dict[str, Any] = {}

    # KPI — buckets computed on la.status (W-APP-01..04), guarded deal lifetime.
    widgets["W-APP-01"] = KpiWidget(value=_safe_int(kpi.get("total")))
    widgets["W-APP-02"] = KpiWidget(value=_safe_int(kpi.get("active")))
    widgets["W-APP-03"] = KpiWidget(value=_safe_int(kpi.get("rejected")))
    widgets["W-APP-04"] = KpiWidget(value=_safe_int(kpi.get("issued")))
    widgets["W-APP-05"] = KpiWidget(value=_safe_float(kpi.get("avg_days")))

    # W-APP-09: deals (issued) KPI — same count as W-APP-04, kept as a distinct card.
    widgets["W-APP-09"] = KpiWidget(value=_safe_int(kpi.get("issued")))

    # W-APP-10: detailed per-status statistics (code + russian label + count).
    widgets["W-APP-10"] = [
        {
            "status": r.get("status"),
            "status_label": lca_status_label(r.get("status")),
            "count": _safe_int(r.get("cnt")),
        }
        for r in status_stats
    ]

    # W-APP-06: combo chart — applications current vs previous period
    if app_timeline:
        app_labels = _build_month_labels(app_timeline)
        app_data = [
            {"x": _to_iso(r.get("month")), "y": _safe_int(r.get("cnt"))}
            for r in app_timeline
        ]
        widgets["W-APP-06"] = ComboChartData(
            labels=app_labels,
            barDatasets=[
                BarChartSeries(
                    name="Заявки текущего периода",
                    color="#4DA2F1",
                    data=[p["y"] for p in app_data],
                )
            ],
        )

    # W-APP-07: combo chart — deals current vs previous
    if deal_timeline:
        deal_labels = _build_month_labels(deal_timeline)
        deal_data = [
            {"x": _to_iso(r.get("month")), "y": _safe_int(r.get("cnt"))}
            for r in deal_timeline
        ]
        widgets["W-APP-07"] = ComboChartData(
            labels=deal_labels,
            barDatasets=[
                BarChartSeries(
                    name="Сделки текущего периода",
                    color="#2E7D32",
                    data=[p["y"] for p in deal_data],
                )
            ],
        )

    # W-APP-08: table — add granular russian status_label per row.
    app_items: list[dict[str, Any]] = []
    for r in table_rows:
        item = dict(r)
        item["status_label"] = lca_status_label(item.get("status"))
        _display_model_item(item)
        app_items.append(item)
    widgets["W-APP-08"] = PaginatedTable(
        items=app_items,
        pagination=_build_pagination(total, page, limit),
    )

    return JSONResponse(
        content=jsonable_encoder(
            DistributorAnalyticsResponse(
                tab="applications",
                filters_applied=filters,
                widgets=widgets,
            )
        )
    )


# ---------------------------------------------------------------------------
# exchange  —  GET /api/v1/distributor/analytics/exchange
# ---------------------------------------------------------------------------
@router.get(
    "/exchange",
    response_model=DistributorAnalyticsResponse,
    summary="[distributor] Аналитика по бирже",
    description="KPI, линейный график заявок и ставок, таблица.",
)
async def exchange_analytics(
    user: Annotated[dict[str, Any], Depends(require_roles(*SUPPORTED_ROLES))],
    session: Annotated[AsyncSession, Depends(get_db)],
    period_from: date | None = Query(default=None),
    period_to: date | None = Query(default=None),
    cities: list[str] | None = Query(default=None),
    marks: list[str] | None = Query(default=None),
    models: list[str] | None = Query(default=None),
    dealers: list[UUID] | None = Query(default=None),
    leasing_companies: list[str] | None = Query(default=None),
    statuses: list[str] | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
) -> JSONResponse:
    scope_id = _get_scope_id(user)
    scope_dealer_ids = await _resolve_scope_dealer_ids(user, session)
    # Exchange data is request/vehicle-based; period + dealer-scope + raw
    # request status map cleanly. Other params are accepted for contract parity.
    filters = _filters_from_query(period_from, period_to, cities, marks, models, dealers, statuses)

    try:
        kpi = await get_distributor_exchange_kpi(
            scope_id, period_from, period_to,
            scope_dealer_ids=scope_dealer_ids, statuses=statuses,
        )
        timeline = await get_distributor_exchange_timeline(
            scope_id, period_from, period_to,
            scope_dealer_ids=scope_dealer_ids, statuses=statuses,
        )
        table_rows, total = await get_distributor_exchange_table(
            scope_id, period_from, period_to, page=page, limit=limit,
            scope_dealer_ids=scope_dealer_ids, statuses=statuses,
        )
    except Exception as exc:
        logger.warning("distributor_exchange_analytics_failed err=%s", exc)
        raise HTTPException(
            status_code=503, detail={"error": "Аналитика временно недоступна"}
        ) from exc

    widgets: dict[str, Any] = {}

    # KPI
    widgets["W-EXC-01"] = KpiWidget(value=_safe_int(kpi.get("total_requests")))
    widgets["W-EXC-02"] = KpiWidget(value=_safe_int(kpi.get("active_requests")))
    widgets["W-EXC-03"] = KpiWidget(value=_safe_int(kpi.get("total_bids")))
    widgets["W-EXC-04"] = KpiWidget(value=_safe_int(kpi.get("accepted_bids")))
    widgets["W-EXC-05"] = KpiWidget(value=_safe_float(kpi.get("avg_price")))

    # W-EXC-06: line chart — requests vs bids
    if timeline:
        # Separate into requests and bids series
        req_points: list[dict[str, Any]] = []
        bid_points: list[dict[str, Any]] = []
        labels_seen: set[str] = set()
        for r in timeline:
            month_str = _to_iso(r.get("month"))
            labels_seen.add(month_str)
            if r.get("kind") == "requests":
                req_points.append({"x": month_str, "y": _safe_int(r.get("cnt"))})
            else:
                bid_points.append({"x": month_str, "y": _safe_int(r.get("cnt"))})

        all_labels = sorted(labels_seen)
        req_map = {p["x"]: p["y"] for p in req_points}
        bid_map = {p["x"]: p["y"] for p in bid_points}
        req_aligned = [TimeSeriesPoint(x=lbl, y=req_map.get(lbl, 0)) for lbl in all_labels]
        bid_aligned = [TimeSeriesPoint(x=lbl, y=bid_map.get(lbl, 0)) for lbl in all_labels]

        widgets["W-EXC-06"] = [
            LineChartSeries(name="Заявки", color="#4DA2F1", data=req_aligned),
            LineChartSeries(name="Ставки", color="#FF9800", data=bid_aligned, dashed=True),
        ]

    # W-EXC-07: table — drop request_id, map discount_type to russian, clamp
    # percent discounts to 0..100, expose bids_count/accepted_bids/average_price.
    exc_items: list[dict[str, Any]] = []
    for r in table_rows:
        row = dict(r)
        dtype = row.get("discount_type")
        row["discount_type_label"] = discount_label(dtype)
        row["discount_value"] = clamp_discount_value(dtype, row.get("discount_value"))
        row["bids_count"] = _safe_int(row.get("bids_count"))
        row["accepted_bids"] = _safe_int(row.get("accepted_bids"))
        avg_price = row.get("average_price")
        row["average_price"] = _safe_float(avg_price) if avg_price is not None else None
        row["status_label"] = exchange_status_label(row.get("status"))
        _display_model_item(row)
        row.pop("request_id", None)
        exc_items.append(row)
    widgets["W-EXC-07"] = PaginatedTable(
        items=exc_items,
        pagination=_build_pagination(total, page, limit),
    )

    return JSONResponse(
        content=jsonable_encoder(
            DistributorAnalyticsResponse(
                tab="exchange",
                filters_applied=filters,
                widgets=widgets,
            )
        )
    )


# ---------------------------------------------------------------------------
# financials  —  GET /api/v1/distributor/analytics/financials
# ---------------------------------------------------------------------------
@router.get(
    "/financials",
    response_model=DistributorAnalyticsResponse,
    summary="[distributor] Финансовая аналитика",
    description="KPI по пайплайну, одобренным и выданным суммам, ставкам, срокам. "
    "Линейный график approved vs issued, таблица.",
)
async def financials_analytics(
    user: Annotated[dict[str, Any], Depends(require_roles(*SUPPORTED_ROLES))],
    session: Annotated[AsyncSession, Depends(get_db)],
    period_from: date | None = Query(default=None),
    period_to: date | None = Query(default=None),
    cities: list[str] | None = Query(default=None),
    marks: list[str] | None = Query(default=None),
    models: list[str] | None = Query(default=None),
    dealers: list[UUID] | None = Query(default=None),
    leasing_companies: list[str] | None = Query(default=None),
    statuses: list[str] | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
) -> JSONResponse:
    scope_id = _get_scope_id(user)
    scope_dealer_ids = await _resolve_scope_dealer_ids(user, session)
    filters = _filters_from_query(period_from, period_to, cities, marks, models, dealers, statuses)
    common: dict[str, Any] = {
        "cities": cities, "marks": marks, "models": models, "dealers": dealers,
        "leasing_companies": leasing_companies, "statuses": statuses,
        "scope_dealer_ids": scope_dealer_ids,
    }

    try:
        kpi = await get_distributor_financials_kpi(
            scope_id, period_from, period_to, **common,
        )
        timeline_data = await get_distributor_financials_timeline(
            scope_id, period_from, period_to, **common,
        )
        table_rows, total = await get_distributor_financials_table(
            scope_id, period_from, period_to,
            page=page, limit=limit, **common,
        )
    except Exception as exc:
        logger.warning("distributor_financials_analytics_failed err=%s", exc)
        raise HTTPException(
            status_code=503, detail={"error": "Аналитика временно недоступна"}
        ) from exc

    widgets: dict[str, Any] = {}

    # KPI widgets — ₽ amounts (01-03), vehicle counts (01a-03a), averages (04-06)
    widgets["W-FIN-01"] = KpiWidget(value=_safe_float(kpi.get("pipeline_amount")))
    widgets["W-FIN-01a"] = KpiWidget(value=_safe_int(kpi.get("pipeline_count")))
    widgets["W-FIN-02"] = KpiWidget(value=_safe_float(kpi.get("approved_amount")))
    widgets["W-FIN-02a"] = KpiWidget(value=_safe_int(kpi.get("approved_count")))
    widgets["W-FIN-03"] = KpiWidget(value=_safe_float(kpi.get("issued_amount")))
    widgets["W-FIN-03a"] = KpiWidget(value=_safe_int(kpi.get("issued_count")))
    widgets["W-FIN-04"] = KpiWidget(value=_safe_float(kpi.get("avg_rate")))
    widgets["W-FIN-05"] = KpiWidget(value=_safe_float(kpi.get("avg_term")))
    widgets["W-FIN-06"] = KpiWidget(value=_safe_float(kpi.get("avg_down_payment_percent")))

    # W-FIN-07: line chart — approved vs issued
    approved_rows = timeline_data.get("approved") or []
    issued_rows = timeline_data.get("issued") or []
    if approved_rows or issued_rows:
        all_labels_set: set[str] = set()
        for r in approved_rows:
            all_labels_set.add(_to_iso(r.get("month")))
        for r in issued_rows:
            all_labels_set.add(_to_iso(r.get("month")))
        all_labels = sorted(all_labels_set)

        app_map = {_to_iso(r.get("month")): _safe_float(r.get("approved")) for r in approved_rows}
        iss_map = {_to_iso(r.get("month")): _safe_float(r.get("issued")) for r in issued_rows}

        widgets["W-FIN-07"] = [
            LineChartSeries(
                name="Одобрено (₽)",
                color="#4CAF50",
                data=[TimeSeriesPoint(x=lbl, y=app_map.get(lbl, 0)) for lbl in all_labels],
            ),
            LineChartSeries(
                name="Выдано (₽)",
                color="#2196F3",
                data=[TimeSeriesPoint(x=lbl, y=iss_map.get(lbl, 0)) for lbl in all_labels],
                dashed=True,
            ),
        ]

    # W-FIN-08: table
    fin_items: list[dict[str, Any]] = []
    for r in table_rows:
        item = dict(r)
        item["status_label"] = lca_status_label(item.get("status"))
        _display_model_item(item)
        fin_items.append(item)
    widgets["W-FIN-08"] = PaginatedTable(
        items=fin_items,
        pagination=_build_pagination(total, page, limit),
    )

    return JSONResponse(
        content=jsonable_encoder(
            DistributorAnalyticsResponse(
                tab="financials",
                filters_applied=filters,
                widgets=widgets,
            )
        )
    )


# ---------------------------------------------------------------------------
# sales-dc  —  GET /api/v1/distributor/analytics/sales-dc
# ---------------------------------------------------------------------------
@router.get(
    "/sales-dc",
    response_model=DistributorAnalyticsResponse,
    summary="[distributor] Продажи по дилерам",
    description="Агрегация заявок по дилер×месяц.",
)
async def sales_dc_analytics(
    user: Annotated[dict[str, Any], Depends(require_roles(*SUPPORTED_ROLES))],
    session: Annotated[AsyncSession, Depends(get_db)],
    period_from: date | None = Query(default=None),
    period_to: date | None = Query(default=None),
    cities: list[str] | None = Query(default=None),
    marks: list[str] | None = Query(default=None),
    models: list[str] | None = Query(default=None),
    dealers: list[UUID] | None = Query(default=None),
    leasing_companies: list[str] | None = Query(default=None),
    statuses: list[str] | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
) -> JSONResponse:
    scope_id = _get_scope_id(user)
    scope_dealer_ids = await _resolve_scope_dealer_ids(user, session)
    filters = _filters_from_query(period_from, period_to, cities, marks, models, dealers, statuses)

    try:
        rows, total = await get_distributor_sales_dc(
            scope_id, period_from, period_to,
            cities=cities, marks=marks, models=models, dealers=dealers,
            leasing_companies=leasing_companies, statuses=statuses,
            page=page, limit=limit,
            scope_dealer_ids=scope_dealer_ids,
        )
    except Exception as exc:
        logger.warning("distributor_sales_dc_failed err=%s", exc)
        raise HTTPException(
            status_code=503, detail={"error": "Аналитика временно недоступна"}
        ) from exc

    app_items: list[dict[str, Any]] = []
    sale_items: list[dict[str, Any]] = []
    for r in rows:
        month = (_to_iso(r.get("month")) or "")[:7] or "—"
        dealer = r.get("dealer_name")
        na = _safe_int(r.get("new_applications"))
        ap = _safe_int(r.get("approved_applications"))
        fi = _safe_int(r.get("financed_applications"))
        app_items.append({
            "month": month, "dealer_name": dealer,
            "new_applications": na, "new_clients": _safe_int(r.get("new_clients")),
            "approved_applications": ap, "approved_clients": _safe_int(r.get("approved_clients")),
            "financed_applications": fi, "financed_clients": _safe_int(r.get("financed_clients")),
            "approval_rate": round(ap / na * 100, 2) if na else 0.0,
            "financing_rate": round(fi / na * 100, 2) if na else 0.0,
        })
        sale_items.append({
            "month": month, "dealer_name": dealer,
            "avg_vehicle_cost": _safe_float(r.get("avg_vehicle_cost")),
            "avg_contract_amount": _safe_float(r.get("avg_contract_amount")),
            "avg_down_payment_percent": _safe_float(r.get("avg_down_payment_percent")),
            "avg_down_payment_amount": _safe_float(r.get("avg_down_payment_amount")),
            "avg_lease_term": round(_safe_float(r.get("avg_lease_term")), 1),
            "avg_rate": _safe_float(r.get("avg_rate")),
            "accessories_total": 0.0, "accessories_percent": 0.0,
        })

    widgets: dict[str, Any] = {
        "W-SDC-01": PaginatedTable(
            items=app_items,
            pagination=_build_pagination(total, page, limit),
        ),
        "W-SDC-02": PaginatedTable(
            items=sale_items,
            pagination=_build_pagination(total, page, limit),
        ),
    }

    return JSONResponse(
        content=jsonable_encoder(
            DistributorAnalyticsResponse(
                tab="sales-dc",
                filters_applied=filters,
                widgets=widgets,
            )
        )
    )


# ---------------------------------------------------------------------------
# sales-dc-regions  —  GET /api/v1/distributor/analytics/sales-dc-regions
# ---------------------------------------------------------------------------
@router.get(
    "/sales-dc-regions",
    response_model=DistributorAnalyticsResponse,
    summary="[distributor] Продажи по регионам",
    description="Пивот по марка×город×месяц.",
)
async def sales_dc_regions_analytics(
    user: Annotated[dict[str, Any], Depends(require_roles(*SUPPORTED_ROLES))],
    session: Annotated[AsyncSession, Depends(get_db)],
    period_from: date | None = Query(default=None),
    period_to: date | None = Query(default=None),
    cities: list[str] | None = Query(default=None),
    marks: list[str] | None = Query(default=None),
    models: list[str] | None = Query(default=None),
    dealers: list[UUID] | None = Query(default=None),
    leasing_companies: list[str] | None = Query(default=None),
    statuses: list[str] | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
) -> JSONResponse:
    scope_id = _get_scope_id(user)
    scope_dealer_ids = await _resolve_scope_dealer_ids(user, session)
    filters = _filters_from_query(period_from, period_to, cities, marks, models, dealers, statuses)

    try:
        res = await get_distributor_sales_dc_regions(
            scope_id, period_from, period_to,
            cities=cities, marks=marks, models=models, dealers=dealers,
            leasing_companies=leasing_companies, statuses=statuses,
            page=page, limit=limit,
            scope_dealer_ids=scope_dealer_ids,
        )
    except Exception as exc:
        logger.warning("distributor_sales_dc_regions_failed err=%s", exc)
        raise HTTPException(
            status_code=503, detail={"error": "Аналитика временно недоступна"}
        ) from exc

    cols = ["Заявок", "Сумма, ₽"]
    mark_items = [
        {
            "month": (_to_iso(r.get("month")) or "")[:7] or "—",
            "mark": r.get("mark"),
            "model_raw": r.get("model"),
            "model": model_display_label(r.get("model")),
            "Заявок": _safe_int(r.get("cnt")),
            "Сумма, ₽": _safe_float(r.get("total_amount")),
        }
        for r in res.get("mark_rows", [])
    ]
    city_items = [
        {
            "month": (_to_iso(r.get("month")) or "")[:7] or "—",
            "city": r.get("city"),
            "Заявок": _safe_int(r.get("cnt")),
            "Сумма, ₽": _safe_float(r.get("total_amount")),
        }
        for r in res.get("city_rows", [])
    ]
    widgets: dict[str, Any] = {
        "W-SDR-01": {
            "items": mark_items, "columns": cols,
            "pagination": _build_pagination(_safe_int(res.get("mark_total")), page, limit),
        },
        "W-SDR-02": {
            "items": city_items, "columns": cols,
            "pagination": _build_pagination(_safe_int(res.get("city_total")), page, limit),
        },
    }

    return JSONResponse(
        content=jsonable_encoder(
            DistributorAnalyticsResponse(
                tab="sales-dc-regions",
                filters_applied=filters,
                widgets=widgets,
            )
        )
    )


# ---------------------------------------------------------------------------
# team  —  GET /api/v1/distributor/analytics/team  (stub — not implemented)
# ---------------------------------------------------------------------------
@router.get(
    "/team",
    response_model=DistributorAnalyticsResponse,
    summary="[distributor] Командная аналитика (заглушка)",
    description="Заглушка. Командная аналитика будет реализована позже.",
)
async def team_analytics(
    user: Annotated[dict[str, Any], Depends(require_roles(*SUPPORTED_ROLES))],
) -> JSONResponse:
    filters = _filters_from_query(None, None, None, None, None, None, None)

    widgets: dict[str, Any] = {
        "empty": True,
        "message": "Командная аналитика пока не реализована",
    }

    return JSONResponse(
        content=jsonable_encoder(
            DistributorAnalyticsResponse(
                tab="team",
                filters_applied=filters,
                widgets=widgets,
            )
        )
    )
