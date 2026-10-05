"""Fire-and-forget publisher for status-change events on Kafka.

FastAPI emits these whenever a trackable entity status changes.
The event-worker persists them to ClickHouse.

Failure policy: never raise. A broken pipe to Kafka must not block
business operations. Failures are logged at WARNING and dropped.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from infrastructure.messaging.broker import get_broker
from infrastructure.messaging.topics import (
    CLIENT_STATUS_CHANGED,
    COMPANY_STATUS_CHANGED,
    DOCUMENT_STATUS_CHANGED,
    EXCHANGE_BID_STATUS_CHANGED,
    EXCHANGE_REQUEST_STATUS_CHANGED,
    LCA_STATUS_CHANGED,
    LEASING_APP_STATUS_CHANGED,
    VEHICLE_STATUS_CHANGED,
    WAREHOUSE_STATUS_CHANGED,
)

logger = logging.getLogger("carcraft-backend")

_tasks: set[asyncio.Task[None]] = set()


def _serialize_value(value: Any) -> Any:
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, dict):
        return {k: _serialize_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_serialize_value(v) for v in value]
    return value


def emit(topic: str, /, **fields: Any) -> None:
    """Schedule a non-blocking publish of a status-change event to Kafka."""
    pending_before = len(_tasks)
    serialized_fields = {k: _serialize_value(v) for k, v in fields.items()}
    task = asyncio.create_task(_publish(topic, serialized_fields))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    logger.debug(
        "status_emit_scheduled topic=%s pending_before=%d pending_after=%d",
        topic,
        pending_before,
        len(_tasks),
    )


async def _publish(topic: str, fields: dict[str, Any]) -> None:
    payload: dict[str, Any] = {
        "timestamp": datetime.now(UTC).isoformat(),
        **fields,
    }
    try:
        await get_broker().publish(payload, topic=topic)
    except Exception as exc:
        logger.warning("status_event_publish_failed topic=%s err=%s", topic, exc)
    finally:
        logger.debug(
            "status_emit_done topic=%s pending=%d", topic, len(_tasks)
        )


# ------------------------------------------------------------------
# Convenience wrappers so callers don't import topics directly.
# ------------------------------------------------------------------


def emit_document_status_changed(
    document_id: UUID,
    old_status: str | None,
    new_status: str,
    changed_by: UUID | None = None,
    reason: str | None = None,
    application_id: UUID | None = None,
) -> None:
    emit(
        DOCUMENT_STATUS_CHANGED,
        entity_id=document_id,
        old_status=old_status,
        new_status=new_status,
        changed_by=changed_by,
        comments=reason,
        application_id=application_id,
    )


def emit_leasing_app_status_changed(
    application_id: UUID,
    old_status: str | None,
    new_status: str,
    changed_by: UUID | None = None,
    reason: str | None = None,
    company_id: UUID | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    emit(
        LEASING_APP_STATUS_CHANGED,
        entity_id=application_id,
        old_status=old_status,
        new_status=new_status,
        changed_by=changed_by,
        comments=reason,
        company_id=company_id,
        application_id=application_id,
        payload=payload,
    )


def emit_lca_status_changed(
    lca_id: UUID,
    old_status: str | None,
    new_status: str,
    changed_by: UUID | None = None,
    review_notes: str | None = None,
    decision_comment: str | None = None,
    application_id: UUID | None = None,
    company_id: UUID | None = None,
) -> None:
    emit(
        LCA_STATUS_CHANGED,
        entity_id=lca_id,
        old_status=old_status,
        new_status=new_status,
        changed_by=changed_by,
        comments=review_notes or decision_comment,
        application_id=application_id,
        company_id=company_id,
    )


def emit_client_status_changed(
    user_id: UUID,
    field: str,
    old_value: Any,
    new_value: Any,
    changed_by: UUID | None = None,
    reason: str | None = None,
    company_id: UUID | None = None,
) -> None:
    """Log a change to one of the client's pseudo-status fields.

    ``field`` is the name of the attribute that changed, e.g.
    ``is_active``, ``email_verified``, ``phone_verified``.
    """
    emit(
        CLIENT_STATUS_CHANGED,
        entity_id=user_id,
        old_status=str(old_value) if old_value is not None else None,
        new_status=str(new_value),
        changed_by=changed_by,
        comments=reason,
        company_id=company_id,
        payload={"field": field},
    )


def emit_company_status_changed(
    company_id: UUID,
    field: str,
    old_value: Any,
    new_value: Any,
    changed_by: UUID | None = None,
    reason: str | None = None,
) -> None:
    """Log a change to ``is_active`` or ``enrichment_status``."""
    emit(
        COMPANY_STATUS_CHANGED,
        entity_id=company_id,
        old_status=str(old_value) if old_value is not None else None,
        new_status=str(new_value),
        changed_by=changed_by,
        comments=reason,
        company_id=company_id,
        payload={"field": field},
    )


def emit_warehouse_status_changed(
    warehouse_id: UUID,
    old_status: str | None,
    new_status: str,
    changed_by: UUID | None = None,
    reason: str | None = None,
    company_id: UUID | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    emit(
        WAREHOUSE_STATUS_CHANGED,
        entity_id=warehouse_id,
        old_status=old_status,
        new_status=new_status,
        changed_by=changed_by,
        comments=reason,
        company_id=company_id,
        payload=payload,
    )


def emit_exchange_request_status_changed(
    request_id: UUID,
    old_status: str | None,
    new_status: str,
    changed_by: UUID | None = None,
    reason: str | None = None,
    company_id: UUID | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    emit(
        EXCHANGE_REQUEST_STATUS_CHANGED,
        entity_id=request_id,
        old_status=old_status,
        new_status=new_status,
        changed_by=changed_by,
        comments=reason,
        company_id=company_id,
        payload=payload,
    )


def emit_exchange_bid_status_changed(
    bid_id: UUID,
    old_status: str | None,
    new_status: str,
    changed_by: UUID | None = None,
    reason: str | None = None,
    company_id: UUID | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    emit(
        EXCHANGE_BID_STATUS_CHANGED,
        entity_id=bid_id,
        old_status=old_status,
        new_status=new_status,
        changed_by=changed_by,
        comments=reason,
        company_id=company_id,
        payload=payload,
    )


def emit_vehicle_status_changed(
    vehicle_id: UUID,
    old_status: str | None,
    new_status: str,
    changed_by: UUID | None = None,
    reason: str | None = None,
    company_id: UUID | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    emit(
        VEHICLE_STATUS_CHANGED,
        entity_id=vehicle_id,
        old_status=old_status,
        new_status=new_status,
        changed_by=changed_by,
        comments=reason,
        company_id=company_id,
        payload=payload,
    )
