"""Analytics dashboard API for Leasing Companies (LC).

All endpoints are read-only against ClickHouse DWH.  RLS is enforced
via ``leasing_company_id = current_user.company_id`` in every query.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import logging
from collections.abc import Callable, Coroutine
from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from application.queries import analytics as analytics_queries
from infrastructure.cache import get_redis
from presentation.dependencies.auth import require_roles
from presentation.dependencies.rate_limit import rate_limit_analytics
from presentation.schemas.analytics import (
    ExportQueryParams,
    LkDashboardFilters,
    LkDashboardRequest,
    LkDashboardResponse,
)

logger = logging.getLogger("carcraft-backend")

router = APIRouter(tags=["Analytics"])

CACHE_TTL_SECONDS = 300  # 5 minutes
SUPPORTED_ROLES = ("leasing_company", "distributor")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _get_scope_id(user: dict[str, Any]) -> tuple[str, UUID]:
    """Return (role, scope_id) for the current user.

    * leasing_company  → scope_id = company_id  (leasing company filter)
    * distributor      → scope_id = user.id      (dealer filter via dealer_id)
    """
    role = str(user.get("role", ""))

    def _to_uuid(value: Any) -> UUID:
        if isinstance(value, UUID):
            return value
        if isinstance(value, str):
            try:
                return UUID(value)
            except ValueError:
                pass
        raise HTTPException(
            status_code=403,
            detail={"error": "Некорректный идентификатор области аналитики"},
        )

    if role == "leasing_company":
        company_id = user.get("company_id")
        if company_id is None:
            raise HTTPException(
                status_code=403, detail={"error": "Пользователь не привязан к компании"}
            )
        return (role, _to_uuid(company_id))
    if role == "distributor":
        user_id = user.get("id")
        if user_id is None:
            raise HTTPException(
                status_code=403, detail={"error": "Пользователь не идентифицирован"}
            )
        return (role, _to_uuid(user_id))
    raise HTTPException(
        status_code=403, detail={"error": "Роль не поддерживается для аналитики"}
    )


def _filters_to_dict(filters: LkDashboardFilters) -> dict[str, Any]:
    return {
        "period_from": filters.period_from,
        "period_to": filters.period_to,
        "statuses": filters.statuses,
        "dealers": filters.dealers,
        "marks": filters.marks,
    }


def _cache_key(scope_id: UUID, role: str, tab: str, filters: LkDashboardFilters) -> str:
    filters_dict = filters.model_dump(mode="json")
    filters_hash = hashlib.sha256(
        json.dumps(filters_dict, sort_keys=True).encode()
    ).hexdigest()[:32]
    return f"lk:dashboard:{role}:{scope_id}:{tab}:{filters_hash}"


async def _get_cached(key: str) -> dict[str, Any] | None:
    try:
        redis = get_redis()
        raw = await redis.get(key)
        if raw:
            return dict(json.loads(raw.decode("utf-8")))
    except Exception as exc:
        logger.debug("analytics_cache_get_failed key=%s err=%s", key, exc)
    return None


async def _set_cached(key: str, data: dict[str, Any]) -> None:
    try:
        redis = get_redis()
        await redis.set(
            key,
            json.dumps(data, default=str).encode("utf-8"),
            ex=CACHE_TTL_SECONDS,
        )
    except Exception as exc:
        logger.debug("analytics_cache_set_failed key=%s err=%s", key, exc)


# ---------------------------------------------------------------------------
# Tab dispatch
# ---------------------------------------------------------------------------
_TAB_HANDLERS: dict[
    str,
    Callable[..., Coroutine[Any, Any, dict[str, Any]]],
] = {
    "overview": analytics_queries.get_overview_widgets,
    "applications": analytics_queries.get_applications_widgets,
    "proposals": analytics_queries.get_proposals_widgets,
    "financials": analytics_queries.get_financials_widgets,
}


async def _dispatch_tab(
    tab: str,
    role: str,
    scope_id: UUID,
    filters: LkDashboardFilters,
    limit: int,
    offset: int,
) -> dict[str, Any]:
    handler = _TAB_HANDLERS.get(tab)
    if handler is None:
        raise HTTPException(status_code=400, detail={"error": "Unknown tab"})
    filters_dict = _filters_to_dict(filters)
    if tab == "overview":
        return await handler(role, scope_id, filters_dict)
    return await handler(role, scope_id, filters_dict, limit, offset)


# ---------------------------------------------------------------------------
# Main endpoint
# ---------------------------------------------------------------------------
@router.post(
    "/lk-dashboard",
    response_model=LkDashboardResponse,
    summary="LC Dashboard",
    description="Returns widgets for the selected LC analytics dashboard tab.",
    dependencies=[rate_limit_analytics],
)
async def lk_dashboard(
    body: LkDashboardRequest,
    user: Annotated[dict[str, Any], Depends(require_roles(*SUPPORTED_ROLES))],
) -> LkDashboardResponse:
    role, scope_id = _get_scope_id(user)
    filters = body.filters

    cache_key = _cache_key(scope_id, role, body.tab, filters)
    cached = await _get_cached(cache_key)
    if cached:
        return LkDashboardResponse.model_validate(cached)

    try:
        widgets = await _dispatch_tab(
            body.tab, role, scope_id, filters, body.limit, body.offset
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("analytics_query_failed tab=%s err=%s", body.tab, exc)
        raise HTTPException(
            status_code=503, detail={"error": "Аналитика временно недоступна"}
        ) from exc

    response = LkDashboardResponse(
        tab=body.tab,
        filters_applied=filters,
        widgets=widgets,
    )
    await _set_cached(cache_key, response.model_dump(mode="json"))
    return response


# ---------------------------------------------------------------------------
# Export endpoint
# ---------------------------------------------------------------------------
def _flatten_widgets(widgets: dict[str, Any], tab: str) -> list[dict[str, Any]]:
    """Extract tabular data from widgets for CSV export."""
    table_keys = {
        "overview": "W-OVR-09",
        "applications": "W-APP-08",
        "proposals": "W-PRP-09",
        "financials": "W-FIN-09",
    }
    key = table_keys.get(tab)
    if key and key in widgets:
        data = widgets[key]
        if isinstance(data, dict) and "items" in data:
            return list(data["items"])
    # Fallback: try to find any list of dicts
    for v in widgets.values():
        if isinstance(v, list) and v and isinstance(v[0], dict):
            return list(v)
    return []


@router.get(
    "/export",
    summary="Export dashboard data",
    description="Exports tabular data for the selected tab as CSV.",
    dependencies=[rate_limit_analytics],
)
async def export_dashboard(
    query: Annotated[ExportQueryParams, Depends()],
    user: Annotated[dict[str, Any], Depends(require_roles(*SUPPORTED_ROLES))],
) -> StreamingResponse:
    role, scope_id = _get_scope_id(user)

    if query.format != "csv":
        raise HTTPException(
            status_code=422, detail={"error": "Only CSV format is supported"}
        )

    filters = LkDashboardFilters(
        period_from=query.period_from,
        period_to=query.period_to,
        statuses=query.statuses,
        dealers=query.dealers,
        marks=query.marks,
    )

    try:
        widgets = await _dispatch_tab(
            query.tab, role, scope_id, filters, query.limit, query.offset
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("analytics_export_failed tab=%s err=%s", query.tab, exc)
        raise HTTPException(
            status_code=503, detail={"error": "Аналитика временно недоступна"}
        ) from exc

    rows = _flatten_widgets(widgets, query.tab)
    if not rows:
        raise HTTPException(
            status_code=404, detail={"error": "Нет данных для экспорта"}
        )

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)
    output.seek(0)

    filename = (
        f"analytics_{query.tab}_"
        f"{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}.csv"
    )
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode("utf-8-sig")),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
