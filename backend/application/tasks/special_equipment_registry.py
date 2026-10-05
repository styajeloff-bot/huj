"""Durable cleanup of media detached from the special-equipment registry."""

from __future__ import annotations

import logging
import socket
from datetime import UTC, datetime, timedelta
from typing import Protocol
from uuid import UUID, uuid4

from infrastructure.database import AsyncSessionLocal
from infrastructure.repositories import (
    special_equipment_media_cleanup_repository as cleanup_repo,
)
from infrastructure.services.special_equipment_import_storage import (
    get_special_equipment_import_storage,
)
from infrastructure.taskiq_broker import broker

logger = logging.getLogger("carcraft-backend")

_BATCH_SIZE = 100
_LEASE_SECONDS = 300
_MAX_ATTEMPTS = 8


class MediaDeleteStorage(Protocol):
    async def delete(self, key: str) -> None: ...


def retry_delay_seconds(attempt_count: int) -> int:
    """Return bounded exponential backoff for one failed cleanup attempt."""

    exponent = min(max(attempt_count - 1, 0), 7)
    return min(3600, 30 * (1 << exponent))


async def _mark_completed(job_id: UUID, worker_id: str) -> bool:
    async with AsyncSessionLocal() as session:
        acknowledged = await cleanup_repo.mark_cleanup_completed(
            session,
            job_id=job_id,
            worker_id=worker_id,
        )
        await session.commit()
        return acknowledged


async def _mark_failed(
    job_id: UUID,
    worker_id: str,
    *,
    attempt_count: int,
    error_code: str,
) -> str | None:
    retry_at = datetime.now(UTC) + timedelta(
        seconds=retry_delay_seconds(attempt_count)
    )
    async with AsyncSessionLocal() as session:
        status = await cleanup_repo.mark_cleanup_failed(
            session,
            job_id=job_id,
            worker_id=worker_id,
            error_code=error_code,
            retry_at=retry_at,
            max_attempts=_MAX_ATTEMPTS,
        )
        await session.commit()
        return status


async def _media_reference_exists(storage_key: str) -> bool:
    async with AsyncSessionLocal() as session:
        return await cleanup_repo.media_reference_exists(
            session,
            storage_key=storage_key,
        )


async def cleanup_special_equipment_media_batch(
    *,
    storage: MediaDeleteStorage | None = None,
    limit: int = _BATCH_SIZE,
) -> dict[str, int]:
    """Claim and process one bounded cleanup batch."""

    active_storage = storage or get_special_equipment_import_storage()
    worker_id = f"{socket.gethostname()}:{uuid4()}"
    async with AsyncSessionLocal() as session:
        jobs = await cleanup_repo.claim_cleanup_jobs(
            session,
            worker_id=worker_id,
            limit=limit,
            lease_seconds=_LEASE_SECONDS,
        )
        await session.commit()

    completed = 0
    retried = 0
    failed = 0
    lost_leases = 0
    retained = 0
    for job in jobs:
        job_id = UUID(str(job["id"]))
        storage_key = str(job["storage_key"])
        if await _media_reference_exists(storage_key):
            if await _mark_completed(job_id, worker_id):
                retained += 1
                logger.warning(
                    "special_equipment_media_cleanup_retained_referenced "
                    "job_id=%s",
                    job_id,
                )
            else:
                lost_leases += 1
            continue
        try:
            await active_storage.delete(storage_key)
        except Exception as exc:
            status = await _mark_failed(
                job_id,
                worker_id,
                attempt_count=int(job["attempt_count"]),
                error_code=type(exc).__name__,
            )
            if status == "pending":
                retried += 1
            elif status == "failed":
                failed += 1
            else:
                lost_leases += 1
            logger.warning(
                "special_equipment_media_cleanup_failed job_id=%s "
                "attempt=%s state=%s err=%s",
                job_id,
                job["attempt_count"],
                status or "lease_lost",
                type(exc).__name__,
            )
        else:
            if await _mark_completed(job_id, worker_id):
                completed += 1
            else:
                lost_leases += 1

    if jobs:
        logger.info(
            "special_equipment_media_cleanup_batch claimed=%d completed=%d "
            "retried=%d failed=%d retained=%d lost_leases=%d",
            len(jobs),
            completed,
            retried,
            failed,
            retained,
            lost_leases,
        )
    return {
        "claimed": len(jobs),
        "completed": completed,
        "retried": retried,
        "failed": failed,
        "retained": retained,
        "lost_leases": lost_leases,
    }


@broker.task(
    task_name="special_equipment_registry.cleanup_media",
    schedule=[{"cron": "* * * * *"}],
)
async def cleanup_special_equipment_media_task() -> None:
    await cleanup_special_equipment_media_batch()
