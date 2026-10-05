"""Read-only ClickHouse client for analytics endpoints.

This is an **exception** to the "FastAPI must not touch ClickHouse"
rule (see AGENTS.md).  Read-only analytical queries are permitted because
there is no other service in the architecture that can serve the LC
dashboard in < 300 ms.  All **writes** still go through Kafka → event-worker.

Distributor scoping
-------------------
Every distributor-facing query is scoped by ``scope_dealer_ids`` — the list
of dealer *company ids* linked to the distributor (resolved via
``application.distributor_scope.resolve_distributor_scope`` /
``DistributorScope.dealer_filter``).  Semantics:

* ``None``  → no scope filter (carcraft_employee sees every distributor's data).
* ``[]``    → distributor with no linked dealers; we still emit
  ``dealer_id IN []`` which matches zero rows, so they never see anything.
* ``[...]`` → mart dealer id column ``IN {scope_dealer_ids:Array(UUID)}``.

This is the security boundary: omitting the filter would leak every
company's data to any distributor.
"""

from __future__ import annotations

import logging
import math
import threading
from datetime import date, datetime
from typing import Any
from uuid import UUID

import clickhouse_connect
from clickhouse_connect.driver.client import Client

from infrastructure.settings import settings

logger = logging.getLogger("carcraft-backend")


# ---------------------------------------------------------------------------
# Pure label/mapping dictionaries (shared by SQL builders, the router, and
# unit tests). Keep these module-level and side-effect free.
# ---------------------------------------------------------------------------

# Granular LCA workflow status → russian label (contract §1).
_LCA_STATUS_LABELS: dict[str, str] = {
    "draft": "Черновик",
    "submitted": "Подана",
    "under_review": "На рассмотрении",
    "approved_scoring": "Одобрено (скоринг)",
    "approved_scoring_another_cond": "Одобрено на иных условиях (скоринг)",
    "documents_required": "Требуются документы",
    "under_review_with_docs": "На рассмотрении с доп. документами",
    "rejected_prescoring": "Отклонено (прескоринг)",
    "approved_final": "Одобрено (финально)",
    "approved_final_another_cond": "Одобрено на иных условиях",
    "rejected_approved": "Отклонено (после одобрения)",
    "selected_lc": "Выбрана ЛК",
    "deal": "Сделка (выдано)",
    "closed": "Закрыто",
}

# Warehouse vehicle status → russian label (contract §2).
_WAREHOUSE_STATUS_LABELS: dict[str, str] = {
    "available": "В наличии",
    "reserved": "В резерве",
    "sold": "Продано",
    "in_transit": "В пути",
    "unknown": "Неизвестно",
}

# Exchange request status → russian label.
_EXCHANGE_STATUS_LABELS: dict[str, str] = {
    "active": "Активен",
    "closed": "Закрыт",
    "cancelled": "Отменён",
    "unknown": "Неизвестно",
}

# Exchange discount_type → russian label (contract §3). Real values present in
# the data are ``percent`` and ``fixed``; we also accept the synonyms named in
# the contract. Unknown values fall through unchanged (see ``discount_label``).
_DISCOUNT_TYPE_LABELS: dict[str, str] = {
    "percent": "Процент",
    "percentage": "Процент",
    "fixed": "Фикс. сумма",
    "amount": "Фикс. сумма",
    "Фикс": "Фикс. сумма",
}

# discount_type values that represent a percentage (clamped 0..100).
_PERCENT_DISCOUNT_TYPES = frozenset({"percent", "percentage"})


def lca_status_label(status: Any) -> str:
    """Map a raw LCA status to its russian label, falling back to the raw value."""
    if status is None:
        return ""
    key = str(status)
    return _LCA_STATUS_LABELS.get(key, key)


def exchange_status_label(status: Any) -> str:
    """Map a raw exchange request status to its russian label."""
    if status is None:
        return ""
    key = str(status)
    return _EXCHANGE_STATUS_LABELS.get(key, key)


def model_display_label(value: Any) -> str:
    """Return a human-readable label for imported technical model identifiers."""
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    if "_" not in text:
        return text
    parts = [part for part in text.split("_") if part]
    if len(parts) <= 1:
        return text
    # Imported values often repeat the mark in the first segment:
    # FAW_BESTUNE_B70_NEW -> Bestune B70 New.
    display_parts = parts[1:] if len(parts) > 2 else parts
    return " ".join(part.capitalize() for part in display_parts)


def lca_status_bucket(status: Any) -> str:
    """Bucket a raw LCA status into ``active|rejected|issued`` (contract §1).

    * ``deal``            → ``issued``
    * ``rejected*``       → ``rejected``
    * everything else     → ``active``
    """
    key = str(status or "")
    if key == "deal":
        return "issued"
    if key.startswith("rejected"):
        return "rejected"
    return "active"


def _status_bucket_sql(column: str) -> str:
    """SQL expression mapping ``column`` (a raw LCA status) to a bucket string."""
    return (
        f"multiIf({column} = 'deal', 'issued', "
        f"{column} LIKE 'rejected%', 'rejected', 'active')"
    )


def status_buckets_to_conditions(
    buckets: list[str] | None, column: str
) -> str | None:
    """Translate status *buckets* (active|rejected|issued) into one SQL condition
    on the raw status ``column``. Returns ``None`` when nothing to filter.

    Unknown bucket names are ignored. The fragments are OR-combined and wrapped
    in parentheses so they compose with surrounding ``AND`` conditions.
    """
    if not buckets:
        return None
    frags: list[str] = []
    for b in buckets:
        if b == "issued":
            frags.append(f"{column} = 'deal'")
        elif b == "rejected":
            frags.append(f"{column} LIKE 'rejected%'")
        elif b == "active":
            frags.append(f"({column} != 'deal' AND {column} NOT LIKE 'rejected%')")
    if not frags:
        return None
    return "(" + " OR ".join(frags) + ")"


def discount_label(discount_type: Any) -> str:
    """Map a raw discount_type to its russian label (passthrough on unknown)."""
    if discount_type is None:
        return ""
    key = str(discount_type)
    return _DISCOUNT_TYPE_LABELS.get(key, key)


def clamp_discount_value(discount_type: Any, value: Any) -> float | None:
    """Clamp percent discounts into ``0..100``; pass other types through.

    Returns ``None`` when ``value`` is ``None`` / unparseable.
    """
    if value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(v) or math.isinf(v):
        return None
    if str(discount_type or "") in _PERCENT_DISCOUNT_TYPES:
        if v < 0:
            return 0.0
        if v > 100:
            return 100.0
    return v


# Guarded deal-lifetime expression in DAYS. Callers pass the deal-open and
# deal-close timestamps (submitted_at → created_at), so the span comes from the
# status history (≤ ~3 days) rather than updated_at (= import time), which fixed
# the "1 670 829 days" garbage. Only counts rows with a sane open < close window.
def _deal_duration_days_sql(created: str, updated: str) -> str:
    return (
        f"if({created} IS NOT NULL AND {updated} >= {created} "
        f"AND {created} > toDateTime64('2000-01-01 00:00:00', 3), "
        f"dateDiff('day', {created}, {updated}), NULL)"
    )


class _ClientState:
    client: Client | None = None
    lock = threading.Lock()


def get_clickhouse_readonly_client() -> Client | None:
    """Return the module-level read-only ClickHouse client singleton.

    Returns ``None`` if ClickHouse is not configured (e.g. local dev
    without the service running).
    """
    client = _ClientState.client
    if client is not None:
        return client
    with _ClientState.lock:
        client = _ClientState.client
        if client is not None:
            return client
        try:
            client = clickhouse_connect.get_client(
                host=settings.clickhouse_host,
                port=settings.clickhouse_port,
                username=settings.clickhouse_user,
                password=settings.clickhouse_password,
                database=settings.clickhouse_db,
                settings={"readonly": 1},
                autogenerate_session_id=False,
            )
        except Exception as exc:
            logger.warning("clickhouse_readonly_connect_failed err=%s", exc)
            return None
        _ClientState.client = client
        return client


def set_clickhouse_readonly_client(client: Client | None) -> None:
    """Override the singleton (used by tests)."""
    with _ClientState.lock:
        _ClientState.client = client


async def query_clickhouse(
    query: str,
    params: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Execute a read-only query and return rows as dicts.

    Failures are logged and re-raised so the API layer can return 503.
    """
    import asyncio
    import time

    start = time.monotonic()

    def _run() -> list[dict[str, Any]]:
        client = get_clickhouse_readonly_client()
        if client is None:
            raise RuntimeError("ClickHouse readonly client is not available")
        result = client.query(query, parameters=params)
        columns = result.column_names
        return [dict(zip(columns, row, strict=False)) for row in result.result_rows]

    try:
        rows = await asyncio.to_thread(_run)
    except Exception:
        elapsed = time.monotonic() - start
        logger.warning(
            "query_clickhouse_failed elapsed_ms=%d query=%s",
            int(elapsed * 1000),
            query[:200].replace("\n", " "),
        )
        raise
    else:
        elapsed = time.monotonic() - start
        logger.info(
            "query_clickhouse rows=%d elapsed_ms=%d query=%s",
            len(rows),
            int(elapsed * 1000),
            query[:200].replace("\n", " "),
        )
    return rows


async def count_lca_status_history_baselines() -> int:
    """Return the number of unique LCA baseline rows in the DWH.

    FINAL makes the readiness check insensitive to duplicate Kafka deliveries
    before background ReplacingMergeTree merges complete.
    """
    rows = await query_clickhouse(
        """
        SELECT uniqExact(lca_id) AS baseline_count
        FROM dwh_lca_status_history FINAL
        WHERE is_baseline = 1
        """
    )
    if len(rows) != 1 or "baseline_count" not in rows[0]:
        raise RuntimeError("ClickHouse returned an invalid baseline count")
    return int(rows[0]["baseline_count"])


# ---------------------------------------------------------------------------
# Distributor analytics query functions
# ---------------------------------------------------------------------------


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
        f = float(value)
    except (TypeError, ValueError):
        return 0.0
    if math.isnan(f) or math.isinf(f):
        return 0.0
    return f


def _build_query(base: str, where: str, suffix: str = "") -> str:
    # ``base`` already ends with a ``WHERE `` clause opener; we only append the
    # rendered conditions and any trailing SQL. (Re-adding ``WHERE`` here was a
    # latent bug that produced ``WHERE  WHERE`` and a ClickHouse syntax error.)
    return base + where + suffix


# ---------------------------------------------------------------------------
# Application status funnel
# ---------------------------------------------------------------------------


async def get_application_status_funnel(
    *,
    start_utc: datetime,
    end_utc: datetime,
    selection_mode: str,
    status_codes: tuple[str, ...],
    terminal_statuses: frozenset[str],
    scope_dealer_ids: list[UUID] | None,
) -> list[dict[str, Any]]:
    """Aggregate both funnel columns from the same scoped LCA base set.

    ``None`` scope means the employee-wide view. An empty list deliberately
    matches zero rows. ReplacingMergeTree ``FINAL`` keeps duplicate Kafka
    delivery idempotent at read time until background merges complete.
    """
    conditions = ["changed_at < {end_utc:DateTime64(3, 'UTC')}"]
    params: dict[str, Any] = {
        "start_utc": start_utc,
        "end_utc": end_utc,
        "status_codes": list(status_codes),
        "terminal_statuses": sorted(terminal_statuses),
    }
    if scope_dealer_ids is not None:
        conditions.append(
            "dealer_company_id IN {scope_dealer_ids:Array(UUID)}"
        )
        params["scope_dealer_ids"] = [str(item) for item in scope_dealer_ids]

    if selection_mode == "created_in_period":
        base_condition = (
            "lca_created_at >= {start_utc:DateTime64(3, 'UTC')} "
            "AND lca_created_at < {end_utc:DateTime64(3, 'UTC')}"
        )
    elif selection_mode == "active_during_period":
        base_condition = (
            "lca_created_at < {end_utc:DateTime64(3, 'UTC')} "
            "AND (start_status NOT IN {terminal_statuses:Array(String)} "
            "OR has_period_event = 1)"
        )
    else:
        raise ValueError(f"Unsupported funnel selection mode: {selection_mode}")

    # The interpolated fragments above are selected only from closed enum
    # branches and fixed column expressions; all caller data stays parameterized.
    query = f"""
        WITH
            scoped_events AS (
                SELECT
                    event_id,
                    lca_id,
                    new_status,
                    changed_at,
                    lca_created_at,
                    is_baseline
                FROM dwh_lca_status_history FINAL
                WHERE {' AND '.join(conditions)}
            ),
            per_lca AS (
                SELECT
                    lca_id,
                    min(lca_created_at) AS lca_created_at,
                    argMax(new_status, tuple(changed_at, event_id)) AS end_status,
                    argMaxIf(
                        new_status,
                        tuple(changed_at, event_id),
                        changed_at < {{start_utc:DateTime64(3, 'UTC')}}
                    ) AS start_status,
                    toUInt8(countIf(
                        changed_at >= {{start_utc:DateTime64(3, 'UTC')}}
                        AND changed_at < {{end_utc:DateTime64(3, 'UTC')}}
                        AND is_baseline = 0
                    ) > 0) AS has_period_event,
                    groupUniqArrayIf(
                        new_status,
                        changed_at >= {{start_utc:DateTime64(3, 'UTC')}}
                        AND changed_at < {{end_utc:DateTime64(3, 'UTC')}}
                        AND is_baseline = 0
                        AND new_status IN {{status_codes:Array(String)}}
                    ) AS period_statuses
                FROM scoped_events
                GROUP BY lca_id
            ),
            base_lca AS (
                SELECT lca_id, end_status, period_statuses
                FROM per_lca
                WHERE end_status IN {{status_codes:Array(String)}}
                  AND {base_condition}
            ),
            status_aggregates AS (
                SELECT
                    report_status AS status,
                    uniqExactIf(lca_id, has(period_statuses, report_status))
                        AS events_count,
                    uniqExactIf(lca_id, end_status = report_status)
                        AS end_state_count,
                    uniqExact(lca_id) AS selected_count
                FROM base_lca
                ARRAY JOIN {{status_codes:Array(String)}} AS report_status
                GROUP BY report_status
            ),
            status_dimension AS (
                SELECT arrayJoin({{status_codes:Array(String)}}) AS status
            )
        SELECT
            statuses.status AS status,
            coalesce(aggregates.events_count, 0) AS events_count,
            coalesce(aggregates.end_state_count, 0) AS end_state_count,
            coalesce(aggregates.selected_count, 0) AS selected_count
        FROM status_dimension AS statuses
        LEFT JOIN status_aggregates AS aggregates USING (status)
        ORDER BY indexOf({{status_codes:Array(String)}}, statuses.status)
    """  # noqa: S608
    return await query_clickhouse(query, params)


def _add_scope(
    conditions: list[str],
    params: dict[str, Any],
    scope_dealer_ids: list[UUID] | None,
    column: str,
) -> None:
    """Append the distributor dealer-scope filter to ``conditions``/``params``.

    ``None`` means "no scope" (employee). A list (including empty) is always
    rendered as ``column IN {scope_dealer_ids:Array(UUID)}``; an empty array
    matches zero rows, which is the desired behaviour for a distributor with
    no linked dealers.
    """
    if scope_dealer_ids is None:
        return
    conditions.append(f"{column} IN {{scope_dealer_ids:Array(UUID)}}")
    params["scope_dealer_ids"] = [str(d) for d in scope_dealer_ids]


def _apply_lca_filters(
    conditions: list[str],
    params: dict[str, Any],
    *,
    cities: list[str] | None = None,
    marks: list[str] | None = None,
    models: list[str] | None = None,
    dealers: list[UUID] | None = None,
    leasing_companies: list[str] | None = None,
    statuses: list[str] | None = None,
    status_column: str = "la.lca_status",
) -> None:
    """Append the standard distributor filters onto an LCA (``la``) query.

    Uses the denormalized columns on distributor marts so no extra joins are
    required: ``dealer_city``, ``mark_name``, ``model_name``,
    ``leasing_company_id``, ``dealer_company_id`` and the raw workflow status.
    ``statuses`` are *buckets* (active|rejected|issued).
    """
    if cities:
        conditions.append("la.dealer_city IN {cities:Array(String)}")
        params["cities"] = cities
    if marks:
        conditions.append("coalesce(la.mark_name, la.vehicle_mark_id) IN {marks:Array(String)}")
        params["marks"] = marks
    if models:
        conditions.append("coalesce(la.model_name, la.vehicle_model_id) IN {models:Array(String)}")
        params["models"] = models
    if dealers:
        conditions.append("la.dealer_company_id IN {dealers:Array(UUID)}")
        params["dealers"] = [str(d) for d in dealers]
    if leasing_companies:
        conditions.append("la.leasing_company_id IN {leasing_companies:Array(UUID)}")
        params["leasing_companies"] = [str(lc) for lc in leasing_companies]
    bucket_cond = status_buckets_to_conditions(statuses, status_column)
    if bucket_cond is not None:
        conditions.append(bucket_cond)


def _apply_sales_dc_regions_filters(
    conditions: list[str],
    params: dict[str, Any],
    *,
    cities: list[str] | None = None,
    marks: list[str] | None = None,
    models: list[str] | None = None,
    dealers: list[UUID] | None = None,
    leasing_companies: list[str] | None = None,
    statuses: list[str] | None = None,
) -> None:
    if cities:
        conditions.append("la.dealer_city IN {cities:Array(String)}")
        params["cities"] = cities
    if marks:
        conditions.append("la.mark_id IN {marks:Array(String)}")
        params["marks"] = marks
    if models:
        conditions.append("la.model_id IN {models:Array(String)}")
        params["models"] = models
    if dealers:
        conditions.append("la.dealer_id IN {dealers:Array(UUID)}")
        params["dealers"] = [str(d) for d in dealers]
    if leasing_companies:
        conditions.append("la.leasing_company_id IN {leasing_companies:Array(UUID)}")
        params["leasing_companies"] = [str(lc) for lc in leasing_companies]
    bucket_cond = status_buckets_to_conditions(statuses, "la.lca_status")
    if bucket_cond is not None:
        conditions.append(bucket_cond)


async def get_distributor_warehouse_kpi(
    company_id: UUID,
    period_from: date | None = None,
    period_to: date | None = None,
    cities: list[str] | None = None,
    marks: list[str] | None = None,
    models: list[str] | None = None,
    dealers: list[UUID] | None = None,
    statuses: list[str] | None = None,
    scope_dealer_ids: list[UUID] | None = None,
) -> dict[str, Any]:
    """KPI widgets W-WHS-01 … W-WHS-07: total, available, reserved, sold,
    total_value, dealer_count, avg_price."""
    conditions = ["1 = 1"]
    params: dict[str, Any] = {}
    _add_scope(conditions, params, scope_dealer_ids, "v.dealer_id")
    if period_from:
        conditions.append("v.created_at >= {period_from:Date}")
        params["period_from"] = period_from
    if period_to:
        conditions.append("v.created_at <= {period_to:Date}")
        params["period_to"] = period_to
    if cities:
        conditions.append("v.dealer_city IN {cities:Array(String)}")
        params["cities"] = cities
    if marks:
        conditions.append("v.mark_id IN {marks:Array(String)}")
        params["marks"] = marks
    if models:
        conditions.append("v.model_id IN {models:Array(String)}")
        params["models"] = models
    if dealers:
        conditions.append("v.dealer_id IN {dealers:Array(UUID)}")
        params["dealers"] = [str(d) for d in dealers]
    if statuses:
        conditions.append("v.status IN {statuses:Array(String)}")
        params["statuses"] = statuses
    where = " AND ".join(conditions)
    query = _build_query("""
        SELECT
            count()                                                  AS total,
            countIf(v.status = 'available')                          AS available,
            countIf(v.status = 'reserved')                           AS reserved,
            countIf(v.status = 'sold')                               AS sold,
            sum(coalesce(v.special_price, v.base_price, 0))          AS total_value,
            uniqExact(v.dealer_id)                                   AS dealer_count,
            avg(coalesce(v.special_price, v.base_price))             AS avg_price
        FROM dm_distributor_warehouse AS v
        WHERE """, where, """
    """)
    rows = await query_clickhouse(query, params)
    return rows[0] if rows else {}


async def get_distributor_warehouse_status_donut(
    company_id: UUID,
    period_from: date | None = None,
    period_to: date | None = None,
    cities: list[str] | None = None,
    marks: list[str] | None = None,
    models: list[str] | None = None,
    dealers: list[UUID] | None = None,
    scope_dealer_ids: list[UUID] | None = None,
) -> list[dict[str, Any]]:
    """W-WHS-08: donut by status."""
    conditions = ["1 = 1"]
    params: dict[str, Any] = {}
    _add_scope(conditions, params, scope_dealer_ids, "v.dealer_id")
    if period_from:
        conditions.append("v.created_at >= {period_from:Date}")
        params["period_from"] = period_from
    if period_to:
        conditions.append("v.created_at <= {period_to:Date}")
        params["period_to"] = period_to
    if cities:
        conditions.append("v.dealer_city IN {cities:Array(String)}")
        params["cities"] = cities
    if marks:
        conditions.append("v.mark_id IN {marks:Array(String)}")
        params["marks"] = marks
    if models:
        conditions.append("v.model_id IN {models:Array(String)}")
        params["models"] = models
    if dealers:
        conditions.append("v.dealer_id IN {dealers:Array(UUID)}")
        params["dealers"] = [str(d) for d in dealers]
    where = " AND ".join(conditions)
    query = _build_query("""
        SELECT
            coalesce(v.status, 'unknown')  AS status,
            count()                        AS cnt
        FROM dm_distributor_warehouse AS v
        WHERE """, where, """
        GROUP BY status
        ORDER BY cnt DESC
    """)
    return await query_clickhouse(query, params)


async def get_distributor_warehouse_mark_model_bar(
    company_id: UUID,
    period_from: date | None = None,
    period_to: date | None = None,
    cities: list[str] | None = None,
    marks: list[str] | None = None,
    models: list[str] | None = None,
    dealers: list[UUID] | None = None,
    scope_dealer_ids: list[UUID] | None = None,
) -> list[dict[str, Any]]:
    """W-WHS-09: bar chart by mark/model (top 10)."""
    conditions = ["1 = 1"]
    params: dict[str, Any] = {}
    _add_scope(conditions, params, scope_dealer_ids, "v.dealer_id")
    if period_from:
        conditions.append("v.created_at >= {period_from:Date}")
        params["period_from"] = period_from
    if period_to:
        conditions.append("v.created_at <= {period_to:Date}")
        params["period_to"] = period_to
    if cities:
        conditions.append("v.dealer_city IN {cities:Array(String)}")
        params["cities"] = cities
    if marks:
        conditions.append("v.mark_id IN {marks:Array(String)}")
        params["marks"] = marks
    if models:
        conditions.append("v.model_id IN {models:Array(String)}")
        params["models"] = models
    if dealers:
        conditions.append("v.dealer_id IN {dealers:Array(UUID)}")
        params["dealers"] = [str(d) for d in dealers]
    where = " AND ".join(conditions)
    query = _build_query("""
        SELECT
            coalesce(v.mark_id, '—')   AS mark,
            coalesce(v.model_id, '—')   AS model,
            count()                     AS cnt
        FROM dm_distributor_warehouse AS v
        WHERE """, where, """
        GROUP BY mark, model
        ORDER BY cnt DESC
        LIMIT 10
    """)
    return await query_clickhouse(query, params)


async def get_distributor_warehouse_timeline(
    company_id: UUID,
    period_from: date | None = None,
    period_to: date | None = None,
    cities: list[str] | None = None,
    marks: list[str] | None = None,
    models: list[str] | None = None,
    dealers: list[UUID] | None = None,
    scope_dealer_ids: list[UUID] | None = None,
) -> list[dict[str, Any]]:
    """W-WHS-10: timeline bar chart by month."""
    conditions = ["1 = 1"]
    params: dict[str, Any] = {}
    _add_scope(conditions, params, scope_dealer_ids, "v.dealer_id")
    if period_from:
        conditions.append("v.created_at >= {period_from:Date}")
        params["period_from"] = period_from
    if period_to:
        conditions.append("v.created_at <= {period_to:Date}")
        params["period_to"] = period_to
    if cities:
        conditions.append("v.dealer_city IN {cities:Array(String)}")
        params["cities"] = cities
    if marks:
        conditions.append("v.mark_id IN {marks:Array(String)}")
        params["marks"] = marks
    if models:
        conditions.append("v.model_id IN {models:Array(String)}")
        params["models"] = models
    if dealers:
        conditions.append("v.dealer_id IN {dealers:Array(UUID)}")
        params["dealers"] = [str(d) for d in dealers]
    where = " AND ".join(conditions)
    query = _build_query("""
        SELECT
            toStartOfMonth(assumeNotNull(v.created_at))  AS month,
            count()                                       AS cnt
        FROM dm_distributor_warehouse AS v
        WHERE """, where, """
        GROUP BY month
        ORDER BY month ASC
    """)
    return await query_clickhouse(query, params)


async def get_distributor_warehouse_dealer_table(
    company_id: UUID,
    period_from: date | None = None,
    period_to: date | None = None,
    cities: list[str] | None = None,
    marks: list[str] | None = None,
    models: list[str] | None = None,
    dealers: list[UUID] | None = None,
    page: int = 1,
    limit: int = 20,
    scope_dealer_ids: list[UUID] | None = None,
) -> tuple[list[dict[str, Any]], int]:
    """W-WHS-11: dealer table (dealer_name, count, value)."""
    conditions = ["1 = 1"]
    params: dict[str, Any] = {}
    _add_scope(conditions, params, scope_dealer_ids, "v.dealer_id")
    if period_from:
        conditions.append("v.created_at >= {period_from:Date}")
        params["period_from"] = period_from
    if period_to:
        conditions.append("v.created_at <= {period_to:Date}")
        params["period_to"] = period_to
    if cities:
        conditions.append("v.dealer_city IN {cities:Array(String)}")
        params["cities"] = cities
    if marks:
        conditions.append("v.mark_id IN {marks:Array(String)}")
        params["marks"] = marks
    if models:
        conditions.append("v.model_id IN {models:Array(String)}")
        params["models"] = models
    if dealers:
        conditions.append("v.dealer_id IN {dealers:Array(UUID)}")
        params["dealers"] = [str(d) for d in dealers]
    where = " AND ".join(conditions)
    offset_val = (page - 1) * limit
    params["_limit"] = limit
    params["_offset"] = offset_val

    count_query = _build_query("""
        SELECT uniqExact(v.dealer_id) AS total
        FROM dm_distributor_warehouse AS v
        WHERE """, where, """
    """)
    count_rows = await query_clickhouse(count_query, {k: v for k, v in params.items() if not k.startswith("_")})
    total = _safe_int(count_rows[0]["total"]) if count_rows else 0

    data_query = _build_query("""
        SELECT
            coalesce(v.dealer_name, toString(v.dealer_id))  AS dealer_name,
            count()                                   AS cnt,
            sum(coalesce(v.special_price, v.base_price, 0)) AS total_value
        FROM dm_distributor_warehouse AS v
        WHERE """, where, """
        GROUP BY dealer_name
        ORDER BY cnt DESC
        LIMIT {_limit:UInt32} OFFSET {_offset:UInt32}
    """)
    rows = await query_clickhouse(data_query, params)
    return rows, total


async def get_distributor_warehouse_city_table(
    company_id: UUID,
    period_from: date | None = None,
    period_to: date | None = None,
    cities: list[str] | None = None,
    marks: list[str] | None = None,
    models: list[str] | None = None,
    dealers: list[UUID] | None = None,
    page: int = 1,
    limit: int = 20,
    scope_dealer_ids: list[UUID] | None = None,
) -> tuple[list[dict[str, Any]], int]:
    """W-WHS-12: city table."""
    conditions = ["1 = 1"]
    params: dict[str, Any] = {}
    _add_scope(conditions, params, scope_dealer_ids, "v.dealer_id")
    if period_from:
        conditions.append("v.created_at >= {period_from:Date}")
        params["period_from"] = period_from
    if period_to:
        conditions.append("v.created_at <= {period_to:Date}")
        params["period_to"] = period_to
    if cities:
        conditions.append("v.dealer_city IN {cities:Array(String)}")
        params["cities"] = cities
    if marks:
        conditions.append("v.mark_id IN {marks:Array(String)}")
        params["marks"] = marks
    if models:
        conditions.append("v.model_id IN {models:Array(String)}")
        params["models"] = models
    if dealers:
        conditions.append("v.dealer_id IN {dealers:Array(UUID)}")
        params["dealers"] = [str(d) for d in dealers]
    where = " AND ".join(conditions)
    offset_val = (page - 1) * limit
    params["_limit"] = limit
    params["_offset"] = offset_val

    count_query = _build_query("""
        SELECT uniqExact(coalesce(v.dealer_city, '—')) AS total
        FROM dm_distributor_warehouse AS v
        WHERE """, where, """
    """)
    count_rows = await query_clickhouse(count_query, {k: v for k, v in params.items() if not k.startswith("_")})
    total = _safe_int(count_rows[0]["total"]) if count_rows else 0

    data_query = _build_query("""
        SELECT
            coalesce(v.dealer_city, '—')              AS city,
            count()                                   AS cnt,
            sum(coalesce(v.special_price, v.base_price, 0)) AS total_value
        FROM dm_distributor_warehouse AS v
        WHERE """, where, """
        GROUP BY city
        ORDER BY cnt DESC
        LIMIT {_limit:UInt32} OFFSET {_offset:UInt32}
    """)
    rows = await query_clickhouse(data_query, params)
    return rows, total


# ---------------------------------------------------------------------------
# Applications tab
# ---------------------------------------------------------------------------


async def get_distributor_applications_kpi(
    company_id: UUID,
    period_from: date | None = None,
    period_to: date | None = None,
    statuses: list[str] | None = None,
    cities: list[str] | None = None,
    marks: list[str] | None = None,
    models: list[str] | None = None,
    dealers: list[UUID] | None = None,
    leasing_companies: list[str] | None = None,
    scope_dealer_ids: list[UUID] | None = None,
) -> dict[str, Any]:
    """KPI for applications tab.

    Buckets computed on the LCA workflow column ``la.lca_status`` (contract §1):
    W-APP-01 total, W-APP-02 active, W-APP-03 rejected, W-APP-04 issued.
    W-APP-05 = guarded average deal lifetime in days.
    """
    conditions = ["1 = 1"]
    params: dict[str, Any] = {}
    _add_scope(conditions, params, scope_dealer_ids, "la.dealer_company_id")
    if period_from:
        conditions.append("la.created_at >= {period_from:Date}")
        params["period_from"] = period_from
    if period_to:
        conditions.append("la.created_at <= {period_to:Date}")
        params["period_to"] = period_to
    _apply_lca_filters(
        conditions, params,
        cities=cities, marks=marks, models=models, dealers=dealers,
        leasing_companies=leasing_companies, statuses=statuses,
    )
    where = " AND ".join(conditions)

    query = (
        "SELECT\n"
        "            count(DISTINCT application_id) AS total,\n"
        "            count(DISTINCT if(\n"
        "                la.lca_status != 'deal' AND la.lca_status NOT LIKE 'rejected%',\n"
        "                application_id, null\n"
        "            )) AS active,\n"
        "            count(DISTINCT if(\n"
        "                la.lca_status LIKE 'rejected%', application_id, null\n"
        "            )) AS rejected,\n"
        "            count(DISTINCT if(\n"
        "                la.lca_status = 'deal', application_id, null\n"
        "            )) AS issued,\n"
        "            avgIf(\n"
        "                dateDiff('day', la.submitted_at, la.created_at),\n"
        "                la.submitted_at IS NOT NULL AND la.created_at >= la.submitted_at\n"
        "                AND la.submitted_at > toDateTime64('2000-01-01 00:00:00', 3)\n"
        "            ) AS avg_days\n"
        "        FROM dm_distributor_applications AS la\n"
        "        WHERE " + where + "\n"
        "    "
    )
    rows = await query_clickhouse(query, params)
    return rows[0] if rows else {}


async def get_distributor_applications_status_stats(
    company_id: UUID,
    period_from: date | None = None,
    period_to: date | None = None,
    statuses: list[str] | None = None,
    cities: list[str] | None = None,
    marks: list[str] | None = None,
    models: list[str] | None = None,
    dealers: list[UUID] | None = None,
    leasing_companies: list[str] | None = None,
    scope_dealer_ids: list[UUID] | None = None,
) -> list[dict[str, Any]]:
    """Detailed per-status statistics widget: GROUP BY la.lca_status → rows of
    {status, label (russian), count}. Labels resolved in the router via
    ``_LCA_STATUS_LABELS``."""
    conditions = ["1 = 1"]
    params: dict[str, Any] = {}
    _add_scope(conditions, params, scope_dealer_ids, "la.dealer_company_id")
    if period_from:
        conditions.append("la.created_at >= {period_from:Date}")
        params["period_from"] = period_from
    if period_to:
        conditions.append("la.created_at <= {period_to:Date}")
        params["period_to"] = period_to
    _apply_lca_filters(
        conditions, params,
        cities=cities, marks=marks, models=models, dealers=dealers,
        leasing_companies=leasing_companies, statuses=statuses,
    )
    where = " AND ".join(conditions)
    query = _build_query("""
        SELECT
            coalesce(la.lca_status, 'unknown') AS status,
            count(DISTINCT application_id)   AS cnt
        FROM dm_distributor_applications AS la
        WHERE """, where, """
        GROUP BY status
        ORDER BY cnt DESC
    """)
    return await query_clickhouse(query, params)


async def get_distributor_applications_timeline(
    company_id: UUID,
    period_from: date | None = None,
    period_to: date | None = None,
    statuses: list[str] | None = None,
    cities: list[str] | None = None,
    marks: list[str] | None = None,
    models: list[str] | None = None,
    dealers: list[UUID] | None = None,
    leasing_companies: list[str] | None = None,
    scope_dealer_ids: list[UUID] | None = None,
) -> list[dict[str, Any]]:
    """W-APP-06: combo chart data — applications current vs previous period."""
    conditions = ["1 = 1"]
    params: dict[str, Any] = {}
    _add_scope(conditions, params, scope_dealer_ids, "la.dealer_company_id")
    if period_from:
        conditions.append("la.created_at >= {period_from:Date}")
        params["period_from"] = period_from
    if period_to:
        conditions.append("la.created_at <= {period_to:Date}")
        params["period_to"] = period_to
    _apply_lca_filters(
        conditions, params,
        cities=cities, marks=marks, models=models, dealers=dealers,
        leasing_companies=leasing_companies, statuses=statuses,
    )
    where = " AND ".join(conditions)
    query = _build_query("""
        SELECT
            toStartOfMonth(assumeNotNull(la.created_at))  AS month,
            count(DISTINCT application_id)                AS cnt
        FROM dm_distributor_applications AS la
        WHERE """, where, """
        GROUP BY month
        ORDER BY month ASC
    """)
    return await query_clickhouse(query, params)


async def get_distributor_deals_timeline(
    company_id: UUID,
    period_from: date | None = None,
    period_to: date | None = None,
    statuses: list[str] | None = None,
    cities: list[str] | None = None,
    marks: list[str] | None = None,
    models: list[str] | None = None,
    dealers: list[UUID] | None = None,
    leasing_companies: list[str] | None = None,
    scope_dealer_ids: list[UUID] | None = None,
) -> list[dict[str, Any]]:
    """W-APP-07: combo chart — deals current vs previous."""
    conditions = ["1 = 1", "la.lca_status = 'deal'"]
    params: dict[str, Any] = {}
    _add_scope(conditions, params, scope_dealer_ids, "la.dealer_company_id")
    if period_from:
        conditions.append("la.created_at >= {period_from:Date}")
        params["period_from"] = period_from
    if period_to:
        conditions.append("la.created_at <= {period_to:Date}")
        params["period_to"] = period_to
    # Deals timeline is intrinsically the 'issued' bucket; honour the other
    # dimensional filters but not the status bucket (it would be redundant).
    _apply_lca_filters(
        conditions, params,
        cities=cities, marks=marks, models=models, dealers=dealers,
        leasing_companies=leasing_companies,
    )
    where = " AND ".join(conditions)
    query = _build_query("""
        SELECT
            toStartOfMonth(assumeNotNull(la.updated_at))  AS month,
            count(DISTINCT application_id)                AS cnt
        FROM dm_distributor_applications AS la
        WHERE """, where, """
        GROUP BY month
        ORDER BY month ASC
    """)
    return await query_clickhouse(query, params)


async def get_distributor_applications_table(
    company_id: UUID,
    period_from: date | None = None,
    period_to: date | None = None,
    statuses: list[str] | None = None,
    cities: list[str] | None = None,
    marks: list[str] | None = None,
    models: list[str] | None = None,
    dealers: list[UUID] | None = None,
    leasing_companies: list[str] | None = None,
    page: int = 1,
    limit: int = 20,
    scope_dealer_ids: list[UUID] | None = None,
) -> tuple[list[dict[str, Any]], int]:
    """W-APP-08: applications table.

    Per-row: display_number, created_at, deal_duration_days (guarded), the
    denormalized leasing_company name, dealer_name, mark/model (denormalized),
    total_amount, raw status and the bucket. Status labels are resolved by the
    router via ``_LCA_STATUS_LABELS``.
    """
    conditions = ["1 = 1"]
    params: dict[str, Any] = {}
    _add_scope(conditions, params, scope_dealer_ids, "la.dealer_company_id")
    if period_from:
        conditions.append("la.created_at >= {period_from:Date}")
        params["period_from"] = period_from
    if period_to:
        conditions.append("la.created_at <= {period_to:Date}")
        params["period_to"] = period_to
    _apply_lca_filters(
        conditions, params,
        cities=cities, marks=marks, models=models, dealers=dealers,
        leasing_companies=leasing_companies, statuses=statuses,
    )
    where = " AND ".join(conditions)
    offset_val = (page - 1) * limit
    params["_limit"] = limit
    params["_offset"] = offset_val

    count_query = f"SELECT count(DISTINCT application_id) AS total FROM dm_distributor_applications AS la WHERE {where}"  # noqa: S608
    count_rows = await query_clickhouse(count_query, {k: v for k, v in params.items() if not k.startswith("_")})
    total = _safe_int(count_rows[0]["total"]) if count_rows else 0

    duration = _deal_duration_days_sql("la.submitted_at", "la.created_at")
    bucket = _status_bucket_sql("la.lca_status")
    data_query = _build_query(f"""
        SELECT
            la.display_number             AS display_number,
            la.created_at                 AS created_at,
            {duration}                    AS deal_duration_days,
            la.leasing_company_name       AS leasing_company,
            la.dealer_name               AS dealer_name,
            coalesce(la.mark_name, la.vehicle_mark_id)                  AS mark,
            coalesce(la.model_name, la.vehicle_model_id)                 AS model,
            la.total_amount               AS total_amount,
            la.lca_status                 AS status,
            {bucket}                      AS status_bucket
        FROM dm_distributor_applications AS la
        WHERE """, where, """
        ORDER BY la.created_at DESC
        LIMIT {_limit:UInt32} OFFSET {_offset:UInt32}
    """)  # noqa: S608
    rows = await query_clickhouse(data_query, params)
    return rows, total


# ---------------------------------------------------------------------------
# Exchange tab
# ---------------------------------------------------------------------------


async def get_distributor_exchange_kpi(
    company_id: UUID,
    period_from: date | None = None,
    period_to: date | None = None,
    scope_dealer_ids: list[UUID] | None = None,
    statuses: list[str] | None = None,
) -> dict[str, Any]:
    """KPI: total_requests, active_requests, total_bids, accepted_bids, avg_price.

    Requests are scoped by the dealer that owns the requested vehicle.
    ``statuses`` filters by raw ``er.request_status``.
    """
    conditions = ["1 = 1"]
    params: dict[str, Any] = {}
    if scope_dealer_ids is not None:
        conditions.append("er.requested_dealer_id IN {scope_dealer_ids:Array(UUID)}")
        params["scope_dealer_ids"] = [str(d) for d in scope_dealer_ids]
    if period_from:
        conditions.append("er.created_at >= {period_from:Date}")
        params["period_from"] = period_from
    if period_to:
        conditions.append("er.created_at <= {period_to:Date}")
        params["period_to"] = period_to
    if statuses:
        conditions.append("er.request_status IN {exc_statuses:Array(String)}")
        params["exc_statuses"] = statuses
    where = " AND ".join(conditions)
    query = (
        "SELECT\n"
        "            count()                                         AS total_requests,\n"
        "            countIf(er.request_status = 'active')            AS active_requests,\n"
        "            sum(coalesce(er.bids_count, 0))                  AS total_bids,\n"
        "            sum(coalesce(er.accepted_bids, 0))               AS accepted_bids,\n"
        "            avg(er.average_price)                            AS avg_price\n"
        "        FROM dm_distributor_exchange AS er\n"
        "        WHERE " + where + "\n"
        "    "
    )
    rows = await query_clickhouse(query, params)
    return rows[0] if rows else {}


async def get_distributor_exchange_timeline(
    company_id: UUID,
    period_from: date | None = None,
    period_to: date | None = None,
    scope_dealer_ids: list[UUID] | None = None,
    statuses: list[str] | None = None,
) -> list[dict[str, Any]]:
    """W-EXC-06: line chart (requests vs bids by month)."""
    conditions = ["1 = 1"]
    params: dict[str, Any] = {}
    if scope_dealer_ids is not None:
        conditions.append("er.requested_dealer_id IN {scope_dealer_ids:Array(UUID)}")
        params["scope_dealer_ids"] = [str(d) for d in scope_dealer_ids]
    if period_from:
        conditions.append("er.created_at >= {period_from:Date}")
        params["period_from"] = period_from
    if period_to:
        conditions.append("er.created_at <= {period_to:Date}")
        params["period_to"] = period_to
    if statuses:
        conditions.append("er.request_status IN {exc_statuses:Array(String)}")
        params["exc_statuses"] = statuses
    where = " AND ".join(conditions)
    query = (
        "SELECT\n"
        "            toStartOfMonth(assumeNotNull(er.created_at))  AS month,\n"
        "            'requests'                                    AS kind,\n"
        "            count()                                       AS cnt\n"
        "        FROM dm_distributor_exchange AS er\n"
        "        WHERE " + where + "\n"
        "        GROUP BY month, kind\n"
        "        UNION ALL\n"
        "        SELECT\n"
        "            toStartOfMonth(assumeNotNull(er.created_at))  AS month,\n"
        "            'bids'                                        AS kind,\n"
        "            sum(coalesce(er.bids_count, 0))                AS cnt\n"
        "        FROM dm_distributor_exchange AS er\n"
        "        WHERE " + where + "\n"
        "        GROUP BY month, kind\n"
        "        ORDER BY month ASC, kind\n"
        "    "
    )
    return await query_clickhouse(query, params)


async def get_distributor_exchange_table(
    company_id: UUID,
    period_from: date | None = None,
    period_to: date | None = None,
    page: int = 1,
    limit: int = 20,
    scope_dealer_ids: list[UUID] | None = None,
    statuses: list[str] | None = None,
) -> tuple[list[dict[str, Any]], int]:
    """W-EXC-07: exchange requests table."""
    conditions = ["1 = 1"]
    params: dict[str, Any] = {}
    if scope_dealer_ids is not None:
        conditions.append("er.requested_dealer_id IN {scope_dealer_ids:Array(UUID)}")
        params["scope_dealer_ids"] = [str(d) for d in scope_dealer_ids]
    if period_from:
        conditions.append("er.created_at >= {period_from:Date}")
        params["period_from"] = period_from
    if period_to:
        conditions.append("er.created_at <= {period_to:Date}")
        params["period_to"] = period_to
    if statuses:
        conditions.append("er.request_status IN {exc_statuses:Array(String)}")
        params["exc_statuses"] = statuses
    where = " AND ".join(conditions)
    offset_val = (page - 1) * limit
    params["_limit"] = limit
    params["_offset"] = offset_val

    count_query = f"SELECT count() AS total FROM dm_distributor_exchange AS er WHERE {where}"  # noqa: S608
    count_rows = await query_clickhouse(count_query, {k: v for k, v in params.items() if not k.startswith("_")})
    total = _safe_int(count_rows[0]["total"]) if count_rows else 0

    data_query = _build_query("""
        SELECT
            er.request_status          AS status,
            er.mark                    AS mark,
            er.model                   AS model,
            er.quantity                AS quantity,
            er.discount_type           AS discount_type,
            er.discount_value          AS discount_value,
            er.expiration_date         AS expiration_date,
            er.created_at              AS created_at,
            coalesce(er.bids_count, 0) AS bids_count,
            coalesce(er.accepted_bids, 0) AS accepted_bids,
            er.average_price          AS average_price
        FROM dm_distributor_exchange AS er
        WHERE """, where, """
        ORDER BY er.created_at DESC
        LIMIT {_limit:UInt32} OFFSET {_offset:UInt32}
    """)
    rows = await query_clickhouse(data_query, params)
    return rows, total


# ---------------------------------------------------------------------------
# Financials tab
# ---------------------------------------------------------------------------


async def get_distributor_financials_kpi(
    company_id: UUID,
    period_from: date | None = None,
    period_to: date | None = None,
    marks: list[str] | None = None,
    models: list[str] | None = None,
    cities: list[str] | None = None,
    dealers: list[UUID] | None = None,
    leasing_companies: list[str] | None = None,
    statuses: list[str] | None = None,
    scope_dealer_ids: list[UUID] | None = None,
) -> dict[str, Any]:
    """KPI: pipeline_amount, approved_amount, issued_amount (both ₽ and count),
    avg_rate, avg_term (lease months — legitimate, NOT deal lifetime),
    avg_down_payment_percent.

    Approved/issued buckets read the LCA workflow column ``la.lca_status``.
    """
    conditions = ["1 = 1"]
    params: dict[str, Any] = {}
    _add_scope(conditions, params, scope_dealer_ids, "la.dealer_company_id")
    if period_from:
        conditions.append("la.created_at >= {period_from:Date}")
        params["period_from"] = period_from
    if period_to:
        conditions.append("la.created_at <= {period_to:Date}")
        params["period_to"] = period_to
    _apply_lca_filters(
        conditions, params,
        cities=cities, marks=marks, models=models, dealers=dealers,
        leasing_companies=leasing_companies, statuses=statuses,
    )
    where = " AND ".join(conditions)
    query = _build_query("""
        SELECT
            sum(coalesce(total_amount, 0))                                  AS pipeline_amount,
            uniqExact(vehicle_id)                                            AS pipeline_count,
            sumIf(coalesce(total_amount, 0), la.lca_status LIKE 'approved%') AS approved_amount,
            uniqExactIf(vehicle_id, la.lca_status LIKE 'approved%')          AS approved_count,
            sumIf(coalesce(total_amount, 0), la.lca_status = 'deal')         AS issued_amount,
            uniqExactIf(vehicle_id, la.lca_status = 'deal')                  AS issued_count,
            avg(rate)                                                        AS avg_rate,
            avg(lease_term_months)                                           AS avg_term,
            avg(down_payment_percent)                                        AS avg_down_payment_percent
        FROM dm_distributor_applications AS la
        WHERE """, where, """
    """)
    rows = await query_clickhouse(query, params)
    return rows[0] if rows else {}


async def get_distributor_financials_timeline(
    company_id: UUID,
    period_from: date | None = None,
    period_to: date | None = None,
    marks: list[str] | None = None,
    models: list[str] | None = None,
    cities: list[str] | None = None,
    dealers: list[UUID] | None = None,
    leasing_companies: list[str] | None = None,
    statuses: list[str] | None = None,
    scope_dealer_ids: list[UUID] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """W-FIN-07: line chart (approved vs issued by month)."""
    conditions = ["1 = 1"]
    params: dict[str, Any] = {}
    _add_scope(conditions, params, scope_dealer_ids, "la.dealer_company_id")
    if period_from:
        conditions.append("la.created_at >= {period_from:Date}")
        params["period_from"] = period_from
    if period_to:
        conditions.append("la.created_at <= {period_to:Date}")
        params["period_to"] = period_to
    _apply_lca_filters(
        conditions, params,
        cities=cities, marks=marks, models=models, dealers=dealers,
        leasing_companies=leasing_companies, statuses=statuses,
    )
    where = " AND ".join(conditions)

    approved_query = _build_query("""
        SELECT
            toStartOfMonth(assumeNotNull(la.created_at))  AS month,
            sum(coalesce(total_amount, 0))                AS approved
        FROM dm_distributor_applications AS la
        WHERE """, where, """ AND la.lca_status LIKE 'approved%'
        GROUP BY month
        ORDER BY month ASC
    """)
    issued_query = _build_query("""
        SELECT
            toStartOfMonth(assumeNotNull(la.created_at))  AS month,
            sum(coalesce(total_amount, 0))                AS issued
        FROM dm_distributor_applications AS la
        WHERE """, where, """ AND la.lca_status = 'deal'
        GROUP BY month
        ORDER BY month ASC
    """)
    approved_rows = await query_clickhouse(approved_query, params)
    issued_rows = await query_clickhouse(issued_query, params)
    return {"approved": approved_rows, "issued": issued_rows}


async def get_distributor_financials_table(
    company_id: UUID,
    period_from: date | None = None,
    period_to: date | None = None,
    marks: list[str] | None = None,
    models: list[str] | None = None,
    cities: list[str] | None = None,
    dealers: list[UUID] | None = None,
    leasing_companies: list[str] | None = None,
    statuses: list[str] | None = None,
    page: int = 1,
    limit: int = 20,
    scope_dealer_ids: list[UUID] | None = None,
) -> tuple[list[dict[str, Any]], int]:
    """W-FIN-08: financials table."""
    conditions = ["1 = 1"]
    params: dict[str, Any] = {}
    _add_scope(conditions, params, scope_dealer_ids, "la.dealer_company_id")
    if period_from:
        conditions.append("la.created_at >= {period_from:Date}")
        params["period_from"] = period_from
    if period_to:
        conditions.append("la.created_at <= {period_to:Date}")
        params["period_to"] = period_to
    _apply_lca_filters(
        conditions, params,
        cities=cities, marks=marks, models=models, dealers=dealers,
        leasing_companies=leasing_companies, statuses=statuses,
    )
    where = " AND ".join(conditions)
    offset_val = (page - 1) * limit
    params["_limit"] = limit
    params["_offset"] = offset_val

    count_query = _build_query("""
        SELECT uniqExact(application_id) AS total
        FROM dm_distributor_applications AS la
        WHERE """, where, """
    """)
    count_rows = await query_clickhouse(count_query, {k: v for k, v in params.items() if not k.startswith("_")})
    total = _safe_int(count_rows[0]["total"]) if count_rows else 0

    bucket = _status_bucket_sql("la.lca_status")
    data_query = _build_query(f"""
        SELECT
            la.display_number          AS display_number,
            la.lca_status              AS status,
            {bucket}                   AS status_bucket,
            la.total_amount            AS total_amount,
            la.down_payment            AS down_payment,
            la.total_cost              AS total_cost,
            la.rate                    AS rate,
            la.lease_term_months       AS lease_term_months,
            la.down_payment_percent    AS down_payment_percent,
            la.monthly_payment         AS monthly_payment,
            coalesce(la.mark_name, la.vehicle_mark_id)               AS mark,
            coalesce(la.model_name, la.vehicle_model_id)              AS model,
            la.leasing_company_name    AS leasing_company,
            la.created_at              AS created_at
        FROM dm_distributor_applications AS la
        WHERE """, where, """
        ORDER BY la.created_at DESC
        LIMIT {_limit:UInt32} OFFSET {_offset:UInt32}
    """)  # noqa: S608
    rows = await query_clickhouse(data_query, params)
    return rows, total


# ---------------------------------------------------------------------------
# Sales DC tab
# ---------------------------------------------------------------------------


async def get_distributor_sales_dc(
    company_id: UUID,
    period_from: date | None = None,
    period_to: date | None = None,
    marks: list[str] | None = None,
    models: list[str] | None = None,
    cities: list[str] | None = None,
    dealers: list[UUID] | None = None,
    leasing_companies: list[str] | None = None,
    statuses: list[str] | None = None,
    page: int = 1,
    limit: int = 20,
    scope_dealer_ids: list[UUID] | None = None,
) -> tuple[list[dict[str, Any]], int]:
    """Sales-DC: aggregated by dealer×month from distributor sales mart."""
    conditions = ["1 = 1"]
    params: dict[str, Any] = {}
    _add_scope(conditions, params, scope_dealer_ids, "la.dealer_company_id")
    if period_from:
        conditions.append("la.created_at >= {period_from:Date}")
        params["period_from"] = period_from
    if period_to:
        conditions.append("la.created_at <= {period_to:Date}")
        params["period_to"] = period_to
    _apply_lca_filters(
        conditions, params,
        cities=cities, marks=marks, models=models, dealers=dealers,
        leasing_companies=leasing_companies, statuses=statuses,
        status_column="la.lca_status",
    )
    where = " AND ".join(conditions)
    offset_val = (page - 1) * limit
    params["_limit"] = limit
    params["_offset"] = offset_val
    count_query = _build_query("""
        SELECT count() AS total
        FROM (
            SELECT 1
            FROM dm_distributor_sales_dc AS la
            WHERE """, where, """
            GROUP BY toStartOfMonth(assumeNotNull(la.created_at)), la.dealer_name
        )
    """)
    count_rows = await query_clickhouse(
        count_query, {k: v for k, v in params.items() if not k.startswith("_")}
    )
    total = _safe_int(count_rows[0]["total"]) if count_rows else 0
    # Per month×dealer: application funnel (new/approved/financed, with distinct
    # client counts) + sales averages. Rates + accessories are derived in the
    # router.
    query = _build_query("""
        SELECT
            toStartOfMonth(assumeNotNull(la.created_at))  AS month,
            la.dealer_name                                AS dealer_name,
            uniqExact(la.application_id)                                       AS new_applications,
            uniqExact(la.client_company_id)                                   AS new_clients,
            uniqExactIf(la.application_id, la.lca_status LIKE 'approved%')     AS approved_applications,
            uniqExactIf(la.client_company_id, la.lca_status LIKE 'approved%')  AS approved_clients,
            uniqExactIf(la.application_id, la.lca_status = 'deal')             AS financed_applications,
            uniqExactIf(la.client_company_id, la.lca_status = 'deal')          AS financed_clients,
            avg(la.vehicle_price)                                              AS avg_vehicle_cost,
            avg(la.total_amount)                                              AS avg_contract_amount,
            avg(la.down_payment_percent)                                      AS avg_down_payment_percent,
            avg(la.down_payment)                                              AS avg_down_payment_amount,
            avg(la.lease_term_months)                                         AS avg_lease_term,
            avg(la.rate)                                                      AS avg_rate
        FROM dm_distributor_sales_dc AS la
        WHERE """, where, """
        GROUP BY month, dealer_name
        ORDER BY month ASC, dealer_name
        LIMIT {_limit:UInt32} OFFSET {_offset:UInt32}
    """)
    rows = await query_clickhouse(query, params)
    return rows, total


# ---------------------------------------------------------------------------
# Sales DC Regions tab
# ---------------------------------------------------------------------------


async def get_distributor_sales_dc_regions(
    company_id: UUID,
    period_from: date | None = None,
    period_to: date | None = None,
    marks: list[str] | None = None,
    models: list[str] | None = None,
    cities: list[str] | None = None,
    dealers: list[UUID] | None = None,
    leasing_companies: list[str] | None = None,
    statuses: list[str] | None = None,
    page: int = 1,
    limit: int = 20,
    scope_dealer_ids: list[UUID] | None = None,
) -> dict[str, Any]:
    """Sales-DC-Regions: two breakdowns — by month×mark×model and month×city.

    Returns ``{"mark_rows": [...], "city_rows": [...]}``. The router shapes these
    into the W-SDR-01 / W-SDR-02 dynamic-column tables.
    """
    conditions = ["1 = 1"]
    params: dict[str, Any] = {}
    _add_scope(conditions, params, scope_dealer_ids, "la.dealer_id")
    if period_from:
        conditions.append("la.created_at >= {period_from:Date}")
        params["period_from"] = period_from
    if period_to:
        conditions.append("la.created_at <= {period_to:Date}")
        params["period_to"] = period_to
    _apply_sales_dc_regions_filters(
        conditions, params,
        cities=cities, marks=marks, models=models, dealers=dealers,
        leasing_companies=leasing_companies, statuses=statuses,
    )
    where = " AND ".join(conditions)
    offset_val = (page - 1) * limit
    params["_limit"] = limit
    params["_offset"] = offset_val
    mark_count_query = _build_query("""
        SELECT count() AS total
        FROM (
            SELECT 1
            FROM dm_distributor_sales_dc_regions AS la
            WHERE """, where, """
            GROUP BY
                toStartOfMonth(assumeNotNull(la.created_at)),
                la.mark_id,
                la.model_id
        )
    """)
    city_count_query = _build_query("""
        SELECT count() AS total
        FROM (
            SELECT 1
            FROM dm_distributor_sales_dc_regions AS la
            WHERE """, where, """
            GROUP BY toStartOfMonth(assumeNotNull(la.created_at)), coalesce(la.dealer_city, '—')
        )
    """)
    mark_query = _build_query("""
        SELECT
            toStartOfMonth(assumeNotNull(la.created_at))  AS month,
            coalesce(la.mark_id, '—')                      AS mark,
            coalesce(la.model_id, '—')                     AS model,
            uniqExact(la.application_id)                   AS cnt,
            sum(coalesce(la.application_total_amount, la.total_price, 0)) AS total_amount
        FROM dm_distributor_sales_dc_regions AS la
        WHERE """, where, """
        GROUP BY month, mark, model
        ORDER BY month ASC, mark, model
        LIMIT {_limit:UInt32} OFFSET {_offset:UInt32}
    """)
    city_query = _build_query("""
        SELECT
            toStartOfMonth(assumeNotNull(la.created_at))  AS month,
            coalesce(la.dealer_city, '—')                  AS city,
            uniqExact(la.application_id)                   AS cnt,
            sum(coalesce(la.application_total_amount, la.total_price, 0)) AS total_amount
        FROM dm_distributor_sales_dc_regions AS la
        WHERE """, where, """
        GROUP BY month, city
        ORDER BY month ASC, city
        LIMIT {_limit:UInt32} OFFSET {_offset:UInt32}
    """)
    count_params = {k: v for k, v in params.items() if not k.startswith("_")}
    mark_count_rows = await query_clickhouse(mark_count_query, count_params)
    city_count_rows = await query_clickhouse(city_count_query, count_params)
    mark_rows = await query_clickhouse(mark_query, params)
    city_rows = await query_clickhouse(city_query, params)
    return {
        "mark_rows": mark_rows,
        "mark_total": _safe_int(mark_count_rows[0]["total"]) if mark_count_rows else 0,
        "city_rows": city_rows,
        "city_total": _safe_int(city_count_rows[0]["total"]) if city_count_rows else 0,
    }
