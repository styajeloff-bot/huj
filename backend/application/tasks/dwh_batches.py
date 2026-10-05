"""Durable delivery tasks for DWH batches produced by CSV imports."""
from __future__ import annotations

import logging
import uuid
from datetime import timedelta
from typing import cast

from taskiq import TaskiqEvents
from taskiq.state import TaskiqState

from infrastructure.database import AsyncSessionLocal
from infrastructure.messaging.dwh_events import publish_dwh_batch
from infrastructure.metrics import DWH_DURABLE_BATCHES
from infrastructure.repositories.data_import_dwh_batches_repository import (
    DataImportDwhBatchesRepository,
    DwhBatchRecord,
)
from infrastructure.repositories.data_import_jobs_repository import (
    DataImportJobsRepository,
)
from infrastructure.taskiq_broker import broker

logger = logging.getLogger("carcraft-backend")

MAX_DELIVERY_ATTEMPTS = 5
RECONCILE_LIMIT = 100
STALE_PUBLISHING_AFTER = timedelta(minutes=5)


def _retry_delay(attempts: int) -> timedelta:
    return timedelta(seconds=min(300, 5 * (2 ** max(0, attempts - 1))))


async def _claim_batch(
    batch_id: uuid.UUID, *, already_claimed: bool
) -> DwhBatchRecord | None:
    async with AsyncSessionLocal() as session:
        if already_claimed:
            batch = await DataImportDwhBatchesRepository.get(session, batch_id)
            if batch is None or batch["status"] != "publishing":
                return None
        else:
            batch = await DataImportDwhBatchesRepository.claim_by_id(
                session,
                batch_id,
                stale_after=STALE_PUBLISHING_AFTER,
            )
            if batch is None:
                return None
        await session.commit()
        return cast("DwhBatchRecord", batch)


@broker.task(task_name="data_import.publish_dwh_batch")
async def deliver_dwh_batch(batch_id: str, *, claimed: bool = False) -> None:
    """Publish one durable batch and advance job progress exactly once."""
    batch_uuid = uuid.UUID(batch_id)
    batch = await _claim_batch(batch_uuid, already_claimed=claimed)
    if batch is None:
        return

    try:
        for topic, payloads in batch["payloads"].items():
            if payloads:
                await publish_dwh_batch(topic, payloads)
    except Exception as exc:
        async with AsyncSessionLocal() as session:
            failure = await DataImportDwhBatchesRepository.record_failure(
                session,
                batch_uuid,
                error=str(exc),
                max_attempts=MAX_DELIVERY_ATTEMPTS,
                retry_after=_retry_delay(batch["attempts"]),
            )
            if failure is not None and failure["exhausted"]:
                await DataImportJobsRepository.set_status(
                    session,
                    failure["job_id"],
                    "failed",
                    error=f"DWH publish failed after {failure['attempts']} attempts: {exc}",
                )
            await session.commit()
        if failure is not None:
            DWH_DURABLE_BATCHES.labels(
                result="failed" if failure["exhausted"] else "retry"
            ).inc()
        logger.warning(
            "data_import_dwh_batch_failed batch=%s attempts=%d err=%s",
            batch_uuid,
            batch["attempts"],
            exc,
        )
        return

    async with AsyncSessionLocal() as session:
        transition = await DataImportDwhBatchesRepository.mark_delivered(
            session, batch_uuid
        )
        if transition is not None:
            await DataImportJobsRepository.record_progress(
                session,
                transition["job_id"],
                rows_done_delta=transition["rows_count"],
                new_errors=transition["row_errors"],
            )
            await DataImportJobsRepository.try_finalize(
                session, transition["job_id"]
            )
        await session.commit()
    if transition is not None:
        DWH_DURABLE_BATCHES.labels(result="delivered").inc()


async def _enqueue_claimed_batches(batches: list[DwhBatchRecord]) -> None:
    for batch in batches:
        try:
            await deliver_dwh_batch.kiq(batch_id=str(batch["id"]), claimed=True)
        except Exception as exc:
            # The durable row remains publishing and becomes claimable after
            # STALE_PUBLISHING_AFTER, so a lost Taskiq wake-up is recoverable.
            logger.warning(
                "data_import_dwh_batch_enqueue_failed batch=%s err=%s",
                batch["id"],
                exc,
            )


@broker.task(
    task_name="data_import.reconcile_dwh_batches",
    schedule=[{"cron": "* * * * *"}],
)
async def reconcile_dwh_batches() -> None:
    """Claim pending/stale batches and re-enqueue durable delivery wake-ups."""
    async with AsyncSessionLocal() as session:
        batches = await DataImportDwhBatchesRepository.claim_due(
            session,
            limit=RECONCILE_LIMIT,
            stale_after=STALE_PUBLISHING_AFTER,
        )
        await session.commit()
    await _enqueue_claimed_batches(batches)


async def _reconcile_dwh_batches_on_worker_startup(_state: TaskiqState) -> None:
    try:
        await reconcile_dwh_batches()
    except Exception as exc:  # pragma: no cover - startup recovery is best-effort
        logger.warning("data import DWH batch recovery failed: %s", exc)


broker.add_event_handler(
    TaskiqEvents.WORKER_STARTUP,
    _reconcile_dwh_batches_on_worker_startup,
)


__all__ = ["deliver_dwh_batch", "reconcile_dwh_batches"]
