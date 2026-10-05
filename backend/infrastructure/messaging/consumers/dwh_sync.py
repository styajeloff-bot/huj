"""FastStream consumer that persists DWH snapshot / changed events to ClickHouse.

Subscribes to ``*.snapshot.v1`` and ``*.changed.v1`` topics for all
replicated entities.  The event-worker is the only process that writes
to the DWH tables.

Batch policy: messages are consumed in batches (up to ``kafka_dwh_batch_size``)
and inserted with a single native ``client.insert`` call per table.

``dwh_leasing_applications`` is retired — its events are bridged into
``dwh_leasing_company_applications``: for each application_id in the batch
we query existing LCA rows and merge the application fields into them.

Failure policy: log a warning and commit the offset (drop the batch).
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import date
from typing import Any
from uuid import UUID

from clickhouse_sqlalchemy.types import Date, Nullable

from infrastructure.clickhouse import execute_clickhouse_batch, get_clickhouse_client
from infrastructure.messaging.broker import broker
from infrastructure.messaging.topics import (
    APP_VEHICLE_CHANGED,
    APP_VEHICLE_SNAPSHOT,
    CALCULATION_CREATED,
    CALCULATION_SNAPSHOT,
    COMPANY_CHANGED,
    COMPANY_SNAPSHOT,
    COMPENSATION_CHANGED,
    COMPENSATION_SNAPSHOT,
    DOCUMENT_CHANGED,
    DOCUMENT_SNAPSHOT,
    EXCHANGE_BID_CHANGED,
    EXCHANGE_BID_SNAPSHOT,
    EXCHANGE_REQUEST_CHANGED,
    EXCHANGE_REQUEST_SNAPSHOT,
    LCA_CHANGED,
    LCA_SNAPSHOT,
    LEASING_APPLICATION_CHANGED,
    LEASING_APPLICATION_SNAPSHOT,
    PROPOSAL_CHANGED,
    PROPOSAL_SNAPSHOT,
    PURCHASE_ORDER_CHANGED,
    PURCHASE_ORDER_SNAPSHOT,
    QUESTIONNAIRE_CHANGED,
    QUESTIONNAIRE_SNAPSHOT,
    SUPPORT_PROGRAM_CHANGED,
    SUPPORT_PROGRAM_SNAPSHOT,
    USER_CHANGED,
    USER_SNAPSHOT,
    VEHICLE_CHANGED,
    VEHICLE_SNAPSHOT,
)
from infrastructure.metrics import (
    DWH_BATCH_SIZE,
    DWH_INSERT_DURATION,
    DWH_INSERT_ERRORS,
    DWH_MESSAGES_CONSUMED,
)
from infrastructure.models.clickhouse import (
    DWHApplicationVehicles,
    DWHCalculations,
    DWHCompanies,
    DWHCompensations,
    DWHDocuments,
    DWHExchangeBids,
    DWHExchangeRequests,
    DWHLeasingCompanyApplications,
    DWHLeasingProposals,
    DWHPurchaseOrders,
    DWHQuestionnaires,
    DWHSupportPrograms,
    DWHUsers,
    DWHVehicles,
)
from infrastructure.settings import settings

logger = logging.getLogger("carcraft-backend")

_KAFKA_CONSUMER_KWARGS: dict[str, Any] = {
    "max_poll_records": settings.kafka_dwh_batch_size,
    "fetch_max_wait_ms": int(settings.kafka_dwh_batch_flush_seconds * 1000),
}

# Application-level field names that should be merged from LA events into LCA rows.
_APP_FIELD_NAMES: tuple[str, ...] = (
    "name",
    "email",
    "application_status",
    "total_amount",
    "down_payment",
    "down_payment_percent",
    "lease_term_months",
    "monthly_payment",
    "total_cost",
    "markup",
    "rate",
    "total_interest",
    "buyout_amount",
    "vat_refund",
    "profit_tax_savings",
    "total_savings",
    "selected_leasing_companies",
    "leasing_company_comments",
    "requested_documents",
    "questionnaire_completed",
    "questionnaire_progress",
    "current_stage",
)


def _to_json(value: Any) -> str:
    if value is None:
        return "{}"
    return json.dumps(value, default=str, ensure_ascii=False)


def _coerce(value: Any) -> Any:
    """Coerce a Kafka JSON value into a ClickHouse-friendly Python value."""
    if value is None:
        return None
    if isinstance(value, bool):
        return 1 if value else 0
    if isinstance(value, str) and value.lower() in ("true", "false"):
        return 1 if value.lower() == "true" else 0
    if isinstance(value, list):
        return _to_json(value)
    if isinstance(value, dict):
        return _to_json(value)
    return value


def _columns_from_model(model: Any) -> list[str]:
    """Return column names from a SQLAlchemy declarative model in declaration order."""
    return [col.name for col in model.__table__.columns]


def _is_clickhouse_nullable_column(column: Any) -> bool:
    return str(column.type).startswith("Nullable(")


def _is_clickhouse_date_column(column: Any) -> bool:
    column_type = column.type
    if isinstance(column_type, Nullable):
        column_type = column_type.nested_type
    return isinstance(column_type, Date)


def _defaults_from_model(model: Any) -> dict[str, Any]:
    defaults: dict[str, Any] = {}
    for col in model.__table__.columns:
        if col.default is None or _is_clickhouse_nullable_column(col):
            continue
        default = col.default.arg
        if callable(default):
            continue
        defaults[col.name] = default
    return defaults


def _messages_to_rows(
    messages: list[dict[str, Any]],
    columns: list[str],
    column_defaults: dict[str, Any],
    date_columns: frozenset[str] = frozenset(),
) -> list[list[Any]]:
    rows: list[list[Any]] = []
    for msg in messages:
        if not isinstance(msg, dict):
            logger.warning(
                "dwh_sync_bad_payload type=%s expected=dict", type(msg).__name__
            )
            continue
        row = []
        for col in columns:
            raw = msg.get(col)
            if raw is None and col in column_defaults:
                raw = column_defaults[col]
            if col in date_columns and isinstance(raw, str):
                raw = date.fromisoformat(raw)
            row.append(_coerce(raw))
        rows.append(row)
    return rows


def _make_batch_handler(table: str, model: Any) -> Any:
    columns = _columns_from_model(model)
    column_defaults = _defaults_from_model(model)
    date_columns = frozenset(
        column.name
        for column in model.__table__.columns
        if _is_clickhouse_date_column(column)
    )

    async def handler(messages: list[dict[str, Any]]) -> None:
        batch_len = len(messages)
        DWH_BATCH_SIZE.labels(table=table).observe(batch_len)
        DWH_MESSAGES_CONSUMED.labels(table=table).inc(batch_len)

        rows = _messages_to_rows(messages, columns, column_defaults, date_columns)
        if not rows:
            logger.warning(
                "dwh_sync_empty_rows table=%s messages=%d columns=%d",
                table, batch_len, len(columns),
            )
            return

        try:
            with DWH_INSERT_DURATION.labels(table=table).time():
                await execute_clickhouse_batch(table, columns, rows)
        except Exception:
            DWH_INSERT_ERRORS.labels(table=table).inc()
            raise

    return handler


# ---------------------------------------------------------------------------
# Bridging consumer: merges leasing_application events into dwh_lca rows.
# ---------------------------------------------------------------------------

def _build_app_events_map(
    messages: list[dict[str, Any]],
) -> dict[UUID, dict[str, Any]]:
    app_events: dict[UUID, dict[str, Any]] = {}
    for msg in messages:
        if not isinstance(msg, dict):
            continue
        app_id = _uuid_from_wire(msg.get("application_id"))
        if app_id is None:
            continue
        app_events[app_id] = msg
    return app_events


def _uuid_from_wire(value: Any) -> UUID | None:
    """Parse a Kafka UUID string without accepting legacy numeric IDs."""
    if isinstance(value, UUID):
        return value
    if not isinstance(value, str):
        return None
    try:
        return UUID(value)
    except ValueError:
        return None


def _fetch_lca_rows(
    client: Any,
    app_ids: list[UUID],
    lca_columns: list[str],
) -> list[list[Any]]:
    col_list = ", ".join(lca_columns)
    query = "SELECT " + col_list + " FROM dwh_leasing_company_applications FINAL WHERE application_id IN arrayJoin({ids:Array(UUID)})"  # noqa: S608
    result = client.query(query, parameters={"ids": app_ids})
    return list(result.result_rows)


def _merge_lca_rows(
    rows_raw: list[list[Any]],
    lca_columns: list[str],
    app_events: dict[UUID, dict[str, Any]],
) -> list[list[Any]]:
    col_index = {col: i for i, col in enumerate(lca_columns)}
    merged_rows: list[list[Any]] = []
    for row in rows_raw:
        app_id = row[col_index["application_id"]]
        app_uuid = _uuid_from_wire(app_id)
        if app_uuid is None:
            continue
        event = app_events.get(app_uuid)
        if event is None:
            continue

        new_row = list(row)
        for field in _APP_FIELD_NAMES:
            idx = col_index.get(field)
            if idx is None:
                continue
            raw = event.get("status") if field == "application_status" else event.get(field)
            if raw is not None:
                new_row[idx] = _coerce(raw)
        merged_rows.append(new_row)
    return merged_rows


async def _bridge_la_to_lca(messages: list[dict[str, Any]]) -> None:
    """Merge application-level fields from LA events into existing LCA rows.

    1. Extract unique application_ids from the batch.
    2. Query ClickHouse for existing LCA rows with those application_ids.
    3. For each found row, merge the application fields from the latest
       event for that application_id.
    4. Insert the merged rows — ReplacingMergeTree will overwrite by updated_at.
    """
    if not messages:
        return

    table = "dwh_leasing_company_applications"
    batch_len = len(messages)
    DWH_BATCH_SIZE.labels(table="dwh_leasing_application_bridge").observe(batch_len)
    DWH_MESSAGES_CONSUMED.labels(table="dwh_leasing_application_bridge").inc(batch_len)

    app_events = _build_app_events_map(messages)
    if not app_events:
        return

    app_ids = list(app_events.keys())

    try:
        client = get_clickhouse_client()
        lca_columns = _columns_from_model(DWHLeasingCompanyApplications)
        rows_raw = await asyncio.to_thread(_fetch_lca_rows, client, app_ids, lca_columns)

        if not rows_raw:
            return

        merged_rows = _merge_lca_rows(rows_raw, lca_columns, app_events)

        if merged_rows:
            with DWH_INSERT_DURATION.labels(table="dwh_leasing_application_bridge").time():
                await execute_clickhouse_batch(table, lca_columns, merged_rows)
    except Exception:
        DWH_INSERT_ERRORS.labels(table="dwh_leasing_application_bridge").inc()
        raise


# ---------------------------------------------------------------------------
# Subscribers — snapshot + changed share the same handler per table.
# We subscribe to both topics so the consumer can build a mixed batch.
# ---------------------------------------------------------------------------


@broker.subscriber(
    LEASING_APPLICATION_SNAPSHOT,
    LEASING_APPLICATION_CHANGED,
    group_id=settings.kafka_dwh_consumer_group,
    batch=True,
    **_KAFKA_CONSUMER_KWARGS,
)
async def consume_leasing_application(messages: list[dict[str, Any]]) -> None:
    """Bridge LA events into dwh_leasing_company_applications."""
    await _bridge_la_to_lca(messages)


@broker.subscriber(
    LCA_SNAPSHOT,
    LCA_CHANGED,
    group_id=settings.kafka_dwh_consumer_group,
    batch=True,
    **_KAFKA_CONSUMER_KWARGS,
)
async def consume_lca(messages: list[dict[str, Any]]) -> None:
    await _make_batch_handler(
        "dwh_leasing_company_applications", DWHLeasingCompanyApplications
    )(messages)


@broker.subscriber(
    PROPOSAL_SNAPSHOT,
    PROPOSAL_CHANGED,
    group_id=settings.kafka_dwh_consumer_group,
    batch=True,
    **_KAFKA_CONSUMER_KWARGS,
)
async def consume_proposal(messages: list[dict[str, Any]]) -> None:
    await _make_batch_handler("dwh_leasing_proposals", DWHLeasingProposals)(messages)


@broker.subscriber(
    DOCUMENT_SNAPSHOT,
    DOCUMENT_CHANGED,
    group_id=settings.kafka_dwh_consumer_group,
    batch=True,
    **_KAFKA_CONSUMER_KWARGS,
)
async def consume_document(messages: list[dict[str, Any]]) -> None:
    await _make_batch_handler("dwh_documents", DWHDocuments)(messages)


@broker.subscriber(
    VEHICLE_SNAPSHOT,
    VEHICLE_CHANGED,
    group_id=settings.kafka_dwh_consumer_group,
    batch=True,
    **_KAFKA_CONSUMER_KWARGS,
)
async def consume_vehicle(messages: list[dict[str, Any]]) -> None:
    await _make_batch_handler("dwh_vehicles", DWHVehicles)(messages)


@broker.subscriber(
    APP_VEHICLE_SNAPSHOT,
    APP_VEHICLE_CHANGED,
    group_id=settings.kafka_dwh_consumer_group,
    batch=True,
    **_KAFKA_CONSUMER_KWARGS,
)
async def consume_app_vehicle(messages: list[dict[str, Any]]) -> None:
    await _make_batch_handler("dwh_application_vehicles", DWHApplicationVehicles)(
        messages
    )


@broker.subscriber(
    COMPANY_SNAPSHOT,
    COMPANY_CHANGED,
    group_id=settings.kafka_dwh_consumer_group,
    batch=True,
    **_KAFKA_CONSUMER_KWARGS,
)
async def consume_company(messages: list[dict[str, Any]]) -> None:
    await _make_batch_handler("dwh_companies", DWHCompanies)(messages)


@broker.subscriber(
    USER_SNAPSHOT,
    USER_CHANGED,
    group_id=settings.kafka_dwh_consumer_group,
    batch=True,
    **_KAFKA_CONSUMER_KWARGS,
)
async def consume_user(messages: list[dict[str, Any]]) -> None:
    await _make_batch_handler("dwh_users", DWHUsers)(messages)


@broker.subscriber(
    PURCHASE_ORDER_SNAPSHOT,
    PURCHASE_ORDER_CHANGED,
    group_id=settings.kafka_dwh_consumer_group,
    batch=True,
    **_KAFKA_CONSUMER_KWARGS,
)
async def consume_purchase_order(messages: list[dict[str, Any]]) -> None:
    await _make_batch_handler("dwh_purchase_orders", DWHPurchaseOrders)(messages)


@broker.subscriber(
    CALCULATION_SNAPSHOT,
    CALCULATION_CREATED,
    group_id=settings.kafka_dwh_consumer_group,
    batch=True,
    **_KAFKA_CONSUMER_KWARGS,
)
async def consume_calculation(messages: list[dict[str, Any]]) -> None:
    await _make_batch_handler("dwh_calculations", DWHCalculations)(messages)


@broker.subscriber(
    QUESTIONNAIRE_SNAPSHOT,
    QUESTIONNAIRE_CHANGED,
    group_id=settings.kafka_dwh_consumer_group,
    batch=True,
    **_KAFKA_CONSUMER_KWARGS,
)
async def consume_questionnaire(messages: list[dict[str, Any]]) -> None:
    await _make_batch_handler("dwh_questionnaires", DWHQuestionnaires)(messages)


@broker.subscriber(
    EXCHANGE_REQUEST_SNAPSHOT,
    EXCHANGE_REQUEST_CHANGED,
    group_id=settings.kafka_dwh_consumer_group,
    batch=True,
    **_KAFKA_CONSUMER_KWARGS,
)
async def consume_exchange_request(messages: list[dict[str, Any]]) -> None:
    await _make_batch_handler("dwh_exchange_requests", DWHExchangeRequests)(messages)


@broker.subscriber(
    EXCHANGE_BID_SNAPSHOT,
    EXCHANGE_BID_CHANGED,
    group_id=settings.kafka_dwh_consumer_group,
    batch=True,
    **_KAFKA_CONSUMER_KWARGS,
)
async def consume_exchange_bid(messages: list[dict[str, Any]]) -> None:
    await _make_batch_handler("dwh_exchange_bids", DWHExchangeBids)(messages)


@broker.subscriber(
    SUPPORT_PROGRAM_SNAPSHOT,
    SUPPORT_PROGRAM_CHANGED,
    group_id=settings.kafka_dwh_consumer_group,
    batch=True,
    **_KAFKA_CONSUMER_KWARGS,
)
async def consume_support_program(messages: list[dict[str, Any]]) -> None:
    await _make_batch_handler("dwh_support_programs", DWHSupportPrograms)(messages)


@broker.subscriber(
    COMPENSATION_SNAPSHOT,
    COMPENSATION_CHANGED,
    group_id=settings.kafka_dwh_consumer_group,
    batch=True,
    **_KAFKA_CONSUMER_KWARGS,
)
async def consume_compensation(messages: list[dict[str, Any]]) -> None:
    await _make_batch_handler("dwh_compensations", DWHCompensations)(messages)
