"""Scheduled durable publisher for LCA status-history outbox rows."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from taskiq import TaskiqEvents
from taskiq.state import TaskiqState

from application.services.lca_status_history_baseline import (
    reconcile_lca_status_history_baseline,
)
from infrastructure.database import AsyncSessionLocal
from infrastructure.messaging.broker import get_broker
from infrastructure.messaging.topics import (
    LCA_STATUS_CHANGED,
    LCA_STATUS_CHANGED_V2,
)
from infrastructure.metrics import (
    LCA_HISTORY_MESSAGES_PUBLISHED,
    LCA_HISTORY_OUTBOX_BACKLOG,
    LCA_HISTORY_OUTBOX_OLDEST_AGE_SECONDS,
    LCA_HISTORY_PUBLISH_FAILURES,
)
from infrastructure.repositories import status_history_repository as history_repo
from infrastructure.taskiq_broker import broker

logger = logging.getLogger("carcraft-backend")

PUBLISH_BATCH_SIZE = 200


def _wire_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "hex"):
        return str(value)
    return value


def build_lca_status_history_payload(event: dict[str, Any]) -> dict[str, Any]:
    """Build the stable v2 Kafka contract from one claimed outbox row."""
    return {
        "event_id": _wire_value(event["id"]),
        "lca_id": _wire_value(event["lca_id"]),
        "application_id": _wire_value(event.get("application_id")),
        "old_status": event.get("old_status"),
        "new_status": event["new_status"],
        "changed_at": _wire_value(event["changed_at"]),
        "changed_by": _wire_value(event.get("changed_by")),
        "reason": event.get("reason"),
        "application_created_at": _wire_value(
            event.get("application_created_at")
        ),
        "lca_created_at": _wire_value(event["lca_created_at"]),
        "dealer_company_id": _wire_value(event.get("dealer_company_id")),
        "distributor_id": _wire_value(event.get("distributor_id")),
        "leasing_company_id": _wire_value(event.get("leasing_company_id")),
        "is_baseline": bool(event.get("is_baseline", False)),
    }


def build_legacy_lca_status_payload(event: dict[str, Any]) -> dict[str, Any]:
    """Build the preserved ``lca.status_changed.v1`` wire contract."""
    return {
        "timestamp": _wire_value(event["changed_at"]),
        "entity_id": _wire_value(event["lca_id"]),
        "old_status": event.get("old_status"),
        "new_status": event["new_status"],
        "changed_by": _wire_value(event.get("changed_by")),
        "comments": event.get("reason"),
        "application_id": _wire_value(event.get("application_id")),
        "company_id": _wire_value(event.get("dealer_company_id")),
    }


async def _refresh_outbox_metrics(session: Any) -> dict[str, Any]:
    stats: dict[str, Any] = await history_repo.get_lca_outbox_stats(session)
    now = datetime.now(UTC)
    oldest = stats.get("oldest_changed_at")
    age = max(0.0, (now - oldest).total_seconds()) if oldest else 0.0
    LCA_HISTORY_OUTBOX_BACKLOG.set(stats["backlog"])
    LCA_HISTORY_OUTBOX_OLDEST_AGE_SECONDS.set(age)
    return stats


async def publish_lca_status_history_batch(
    *, limit: int = PUBLISH_BATCH_SIZE
) -> dict[str, int]:
    """Publish one locked batch, recording acknowledgement or retry state."""
    published = 0
    failed = 0
    async with AsyncSessionLocal() as session:
        try:
            events = await history_repo.claim_unpublished_lca_events(
                session,
                limit=limit,
            )
            kafka = get_broker()
            for event in events:
                try:
                    await kafka.publish(
                        build_lca_status_history_payload(event),
                        topic=LCA_STATUS_CHANGED_V2,
                    )
                    if not event.get("is_baseline", False):
                        await kafka.publish(
                            build_legacy_lca_status_payload(event),
                            topic=LCA_STATUS_CHANGED,
                        )
                except Exception as exc:
                    failed += 1
                    LCA_HISTORY_PUBLISH_FAILURES.inc()
                    attempts = await history_repo.mark_lca_event_publish_failed(
                        session,
                        event_id=event["id"],
                        error=str(exc),
                    )
                    logger.warning(
                        "lca_history_publish_failed event_id=%s attempts=%d err=%s",
                        event["id"],
                        attempts,
                        exc,
                    )
                else:
                    published += 1
                    LCA_HISTORY_MESSAGES_PUBLISHED.inc()
                    await history_repo.mark_lca_event_published(
                        session,
                        event_id=event["id"],
                    )
            stats = await _refresh_outbox_metrics(session)
            await session.commit()
        except Exception:
            await session.rollback()
            raise

    if published or failed:
        logger.info(
            "lca_history_publish_batch claimed=%d published=%d failed=%d backlog=%d",
            len(events),
            published,
            failed,
            stats["backlog"],
        )
    return {"claimed": len(events), "published": published, "failed": failed}


@broker.task(
    task_name="lca_status_history.publish",
    schedule=[{"cron": "* * * * *"}],
)
async def publish_lca_status_history_task() -> None:
    await publish_lca_status_history_batch()


@broker.task(
    task_name="lca_status_history.ensure_baseline",
    schedule=[{"cron": "* * * * *"}],
)
async def ensure_lca_status_history_baseline_task() -> None:
    """Reconcile the initial LCA status-history baseline when needed."""
    result = await reconcile_lca_status_history_baseline()
    logger.info(
        "lca_status_history_baseline_reconciled state=%s",
        result.state,
    )


async def _ensure_lca_status_history_baseline_on_worker_startup(
    _state: TaskiqState,
) -> None:
    """Best-effort reconciliation so worker startup never depends on DWH."""
    try:
        await ensure_lca_status_history_baseline_task()
    except Exception as exc:  # pragma: no cover - infrastructure-dependent
        logger.warning(
            "lca status-history baseline recovery failed in taskiq worker: %s",
            exc,
        )


broker.add_event_handler(
    TaskiqEvents.WORKER_STARTUP,
    _ensure_lca_status_history_baseline_on_worker_startup,
)
