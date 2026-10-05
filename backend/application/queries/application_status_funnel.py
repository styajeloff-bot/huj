"""Application query for the historical LCA status funnel."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from hashlib import sha256
from time import perf_counter
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.ext.asyncio import AsyncSession

from application.distributor_scope import resolve_distributor_scope
from application.permissions import get_company_permissions
from domain.application_status_funnel import (
    APPLICATION_FUNNEL_STATUS_CODES,
    APPLICATION_FUNNEL_STATUSES,
    APPLICATION_FUNNEL_TERMINAL_STATUSES,
    ApplicationFunnelSelectionMode,
)
from infrastructure.cache import get_redis
from infrastructure.clickhouse_readonly import get_application_status_funnel
from infrastructure.metrics import (
    APPLICATION_FUNNEL_CACHE_ERRORS,
    APPLICATION_FUNNEL_CACHE_HITS,
    APPLICATION_FUNNEL_ERRORS,
    APPLICATION_FUNNEL_INVARIANT_FAILURES,
    APPLICATION_FUNNEL_QUERY_DURATION_SECONDS,
)
from infrastructure.repositories import status_history_repository
from infrastructure.settings import settings

logger = logging.getLogger("carcraft-backend")

_CACHE_CONTRACT_VERSION = "v1"
_MAX_PERIOD_DAYS = 366


class ApplicationFunnelError(Exception):
    """Expected API error with a stable machine-readable code."""

    def __init__(
        self,
        message: str,
        status_code: int,
        error_code: str,
        *,
        history_available_from: date | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code
        self.history_available_from = history_available_from


@dataclass(frozen=True, slots=True)
class GetApplicationStatusFunnelQuery:
    actor_id: UUID
    actor_role: str
    company_id: UUID | None = None
    period_from: date | None = None
    period_to: date | None = None
    selection_mode: ApplicationFunnelSelectionMode = (
        ApplicationFunnelSelectionMode.CREATED_IN_PERIOD
    )


@dataclass(frozen=True, slots=True)
class ApplicationFunnelPeriod:
    period_from: date
    period_to: date
    start_utc: datetime
    end_utc: datetime


def resolve_application_funnel_period(
    *,
    period_from: date | None,
    period_to: date | None,
    history_available_from: date,
    timezone_name: str,
    now: datetime | None = None,
) -> ApplicationFunnelPeriod:
    """Resolve inclusive Moscow calendar dates to a half-open UTC interval."""
    try:
        timezone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise ApplicationFunnelError(
            "Отчётная таймзона настроена некорректно",
            503,
            "ANALYTICS_UNAVAILABLE",
        ) from exc

    current = now or datetime.now(UTC)
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    today = current.astimezone(timezone).date()
    month_start = today.replace(day=1)

    resolved_from = period_from or max(month_start, history_available_from)
    resolved_to = period_to or today

    if resolved_from < history_available_from:
        raise ApplicationFunnelError(
            f"Достоверная история статусов доступна с {history_available_from.isoformat()}",
            422,
            "HISTORY_NOT_AVAILABLE",
            history_available_from=history_available_from,
        )
    if resolved_from > resolved_to:
        if period_from is None and history_available_from > today:
            raise ApplicationFunnelError(
                f"Достоверная история статусов будет доступна с "
                f"{history_available_from.isoformat()}",
                422,
                "HISTORY_NOT_AVAILABLE",
                history_available_from=history_available_from,
            )
        raise ApplicationFunnelError(
            "Начальная дата периода не может быть позже конечной",
            422,
            "INVALID_DATE_RANGE",
        )
    if (resolved_to - resolved_from).days + 1 > _MAX_PERIOD_DAYS:
        raise ApplicationFunnelError(
            "Период отчёта не может превышать 366 календарных дней",
            422,
            "PERIOD_TOO_LARGE",
        )

    start_local = datetime.combine(resolved_from, time.min, tzinfo=timezone)
    end_local = datetime.combine(
        resolved_to + timedelta(days=1), time.min, tzinfo=timezone
    )
    return ApplicationFunnelPeriod(
        period_from=resolved_from,
        period_to=resolved_to,
        start_utc=start_local.astimezone(UTC),
        end_utc=end_local.astimezone(UTC),
    )


async def _resolve_dealer_scope(
    query: GetApplicationStatusFunnelQuery,
    session: AsyncSession,
) -> list[UUID] | None:
    if query.actor_role == "carcraft_employee":
        return None
    if query.actor_role == "dealer":
        if query.company_id is None:
            raise ApplicationFunnelError(
                "Пользователь не привязан к компании",
                403,
                "ACCESS_DENIED",
            )
        permissions = await get_company_permissions(
            session, query.actor_id, query.company_id
        )
        if not permissions.get("can_view_applications"):
            raise ApplicationFunnelError(
                "Просмотр заявок ограничен администратором компании",
                403,
                "ACCESS_DENIED",
            )
        return [query.company_id]
    if query.actor_role == "distributor":
        if query.company_id is None:
            raise ApplicationFunnelError(
                "Пользователь не привязан к компании",
                403,
                "ACCESS_DENIED",
            )
        scope = await resolve_distributor_scope(
            session,
            actor_id=query.actor_id,
            actor_role=query.actor_role,
            company_id=query.company_id,
        )
        return scope.dealer_filter()
    raise ApplicationFunnelError(
        "Роль не поддерживается для аналитики",
        403,
        "ACCESS_DENIED",
    )


def _cache_key(
    query: GetApplicationStatusFunnelQuery,
    period: ApplicationFunnelPeriod,
    history_available_from: date,
    scope_dealer_ids: list[UUID] | None,
) -> str:
    if scope_dealer_ids is None:
        scope = "all"
    else:
        scope_payload = ",".join(sorted(str(item) for item in scope_dealer_ids))
        scope = sha256(scope_payload.encode()).hexdigest()[:24] if scope_payload else "empty"
    return (
        f"analytics:application-funnel:{_CACHE_CONTRACT_VERSION}:"
        f"{query.actor_role}:{scope}:{period.period_from.isoformat()}:"
        f"{period.period_to.isoformat()}:{query.selection_mode.value}:"
        f"{history_available_from.isoformat()}"
    )


async def _get_cached(key: str) -> dict[str, Any] | None:
    try:
        raw = await get_redis().get(key)
        if raw is None:
            return None
        decoded = raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
        value = json.loads(decoded)
        if isinstance(value, dict):
            APPLICATION_FUNNEL_CACHE_HITS.inc()
            logger.info("application_funnel_cache_hit key=%s", key)
            return value
    except Exception as exc:
        APPLICATION_FUNNEL_CACHE_ERRORS.labels(operation="get").inc()
        logger.debug("application_funnel_cache_get_failed key=%s err=%s", key, exc)
    return None


async def _set_cached(key: str, value: dict[str, Any]) -> None:
    try:
        await get_redis().set(
            key,
            json.dumps(value, ensure_ascii=False).encode("utf-8"),
            ex=settings.analytics_funnel_cache_ttl_seconds,
        )
    except Exception as exc:
        APPLICATION_FUNNEL_CACHE_ERRORS.labels(operation="set").inc()
        logger.debug("application_funnel_cache_set_failed key=%s err=%s", key, exc)


def _safe_count(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _build_response(
    *,
    rows: list[dict[str, Any]],
    period: ApplicationFunnelPeriod,
    selection_mode: ApplicationFunnelSelectionMode,
    history_available_from: date,
) -> dict[str, Any]:
    counts_by_status = {str(row.get("status")): row for row in rows}
    selected_count = _safe_count(rows[0].get("selected_count")) if rows else 0

    response_rows: list[dict[str, Any]] = []
    for status in APPLICATION_FUNNEL_STATUSES:
        raw = counts_by_status.get(status.code, {})
        response_rows.append(
            {
                "status": status.code,
                "label": status.label,
                "order": status.order,
                "events_count": _safe_count(raw.get("events_count")),
                "end_state_count": _safe_count(raw.get("end_state_count")),
            }
        )

    end_state_total = sum(item["end_state_count"] for item in response_rows)
    if end_state_total != selected_count:
        APPLICATION_FUNNEL_INVARIANT_FAILURES.inc()
        logger.error(
            "application_funnel_invariant_failed selected=%d end_state_total=%d",
            selected_count,
            end_state_total,
        )
        raise ApplicationFunnelError(
            "Аналитика временно недоступна",
            503,
            "ANALYTICS_UNAVAILABLE",
        )

    return {
        "unit": "lca",
        "timezone": settings.analytics_timezone,
        "period_from": period.period_from.isoformat(),
        "period_to": period.period_to.isoformat(),
        "selection_mode": selection_mode.value,
        "history_available_from": history_available_from.isoformat(),
        "selected_count": selected_count,
        "rows": response_rows,
    }


async def _handle_get_application_status_funnel(
    query: GetApplicationStatusFunnelQuery,
    session: AsyncSession,
) -> dict[str, Any]:
    """Authorize, validate, cache and execute the historical funnel query."""
    try:
        scope_dealer_ids = await _resolve_dealer_scope(query, session)
    except ApplicationFunnelError:
        raise
    except Exception as exc:
        logger.warning("application_funnel_scope_failed err=%s", exc)
        raise ApplicationFunnelError(
            "Аналитика временно недоступна",
            503,
            "ANALYTICS_UNAVAILABLE",
        ) from exc

    try:
        history_available_from = (
            await status_history_repository.get_history_available_from(session)
        )
    except Exception as exc:
        logger.warning("application_funnel_watermark_failed err=%s", exc)
        raise ApplicationFunnelError(
            "Аналитика временно недоступна",
            503,
            "ANALYTICS_UNAVAILABLE",
        ) from exc
    if history_available_from is None:
        raise ApplicationFunnelError(
            "История статусов ещё не подготовлена",
            503,
            "HISTORY_NOT_READY",
        )

    try:
        period = resolve_application_funnel_period(
            period_from=query.period_from,
            period_to=query.period_to,
            history_available_from=history_available_from,
            timezone_name=settings.analytics_timezone,
        )
        key = _cache_key(query, period, history_available_from, scope_dealer_ids)
        cached = await _get_cached(key)
        if cached is not None:
            return cached

        raw_rows = await get_application_status_funnel(
            start_utc=period.start_utc,
            end_utc=period.end_utc,
            selection_mode=query.selection_mode.value,
            status_codes=APPLICATION_FUNNEL_STATUS_CODES,
            terminal_statuses=APPLICATION_FUNNEL_TERMINAL_STATUSES,
            scope_dealer_ids=scope_dealer_ids,
        )
        response = _build_response(
            rows=raw_rows,
            period=period,
            selection_mode=query.selection_mode,
            history_available_from=history_available_from,
        )
        await _set_cached(key, response)
        return response
    except ApplicationFunnelError:
        raise
    except Exception as exc:
        logger.warning("application_funnel_query_failed err=%s", exc)
        raise ApplicationFunnelError(
            "Аналитика временно недоступна",
            503,
            "ANALYTICS_UNAVAILABLE",
        ) from exc


async def handle_get_application_status_funnel(
    query: GetApplicationStatusFunnelQuery,
    session: AsyncSession,
) -> dict[str, Any]:
    """Measure and expose errors for one funnel request."""
    started_at = perf_counter()
    try:
        return await _handle_get_application_status_funnel(query, session)
    except ApplicationFunnelError as exc:
        APPLICATION_FUNNEL_ERRORS.labels(error_code=exc.error_code).inc()
        raise
    except Exception:
        APPLICATION_FUNNEL_ERRORS.labels(error_code="UNEXPECTED").inc()
        raise
    finally:
        APPLICATION_FUNNEL_QUERY_DURATION_SECONDS.observe(perf_counter() - started_at)
