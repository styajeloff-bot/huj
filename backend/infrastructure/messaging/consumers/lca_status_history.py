"""Kafka v2 consumer for the durable LCA status history read model."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from infrastructure.clickhouse import execute_clickhouse_batch_strict
from infrastructure.messaging.broker import broker
from infrastructure.messaging.topics import LCA_STATUS_CHANGED_V2
from infrastructure.metrics import (
    LCA_HISTORY_CONSUMER_ERRORS,
    LCA_HISTORY_INGEST_LAG_SECONDS,
    LCA_HISTORY_MESSAGES_CONSUMED,
    LCA_HISTORY_ROWS_INSERTED,
)
from infrastructure.settings import settings

_TABLE = "dwh_lca_status_history"
_COLUMNS = [
    "event_id",
    "lca_id",
    "application_id",
    "old_status",
    "new_status",
    "changed_at",
    "changed_by",
    "reason",
    "application_created_at",
    "lca_created_at",
    "dealer_company_id",
    "distributor_id",
    "leasing_company_id",
    "is_baseline",
    "ingested_at",
]


class LcaStatusChangedV2(BaseModel):
    """Validated wire contract for ``lca.status_changed.v2``."""

    model_config = ConfigDict(extra="forbid")

    event_id: UUID
    lca_id: UUID
    application_id: UUID | None = None
    old_status: str | None = None
    new_status: str
    changed_at: datetime
    changed_by: UUID | None = None
    reason: str | None = None
    application_created_at: datetime | None = None
    lca_created_at: datetime
    dealer_company_id: UUID | None = None
    distributor_id: UUID | None = None
    leasing_company_id: UUID | None = None
    is_baseline: bool = False


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("timestamp must include a timezone")
    return value.astimezone(UTC)


def _event_to_row(
    event: LcaStatusChangedV2,
    *,
    ingested_at: datetime,
) -> list[Any]:
    changed_at = _as_utc(event.changed_at)
    lca_created_at = _as_utc(event.lca_created_at)
    application_created_at = (
        _as_utc(event.application_created_at)
        if event.application_created_at is not None
        else None
    )
    return [
        event.event_id,
        event.lca_id,
        event.application_id,
        event.old_status,
        event.new_status,
        changed_at,
        event.changed_by,
        event.reason,
        application_created_at,
        lca_created_at,
        event.dealer_company_id,
        event.distributor_id,
        event.leasing_company_id,
        1 if event.is_baseline else 0,
        ingested_at,
    ]


@broker.subscriber(
    LCA_STATUS_CHANGED_V2,
    group_id=settings.kafka_dwh_consumer_group,
    batch=True,
    max_poll_records=settings.kafka_dwh_batch_size,
    fetch_max_wait_ms=int(settings.kafka_dwh_batch_flush_seconds * 1000),
)
async def consume_lca_status_history(messages: list[dict[str, Any]]) -> None:
    """Validate and insert a batch; any error is raised for Kafka retry."""
    LCA_HISTORY_MESSAGES_CONSUMED.inc(len(messages))
    ingested_at = datetime.now(UTC)
    try:
        events = [LcaStatusChangedV2.model_validate(item) for item in messages]
        rows = [_event_to_row(event, ingested_at=ingested_at) for event in events]
        await execute_clickhouse_batch_strict(_TABLE, _COLUMNS, rows)
    except Exception:
        LCA_HISTORY_CONSUMER_ERRORS.inc()
        raise

    LCA_HISTORY_ROWS_INSERTED.inc(len(rows))
    for event in events:
        LCA_HISTORY_INGEST_LAG_SECONDS.observe(
            max(0.0, (ingested_at - _as_utc(event.changed_at)).total_seconds())
        )
