"""Persistence operations for durable special-equipment media cleanup."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.models.special_equipment import (
    SpecialEquipmentCategory,
    SpecialEquipmentProductImage,
)
from infrastructure.models.special_equipment_registry import (
    SpecialEquipmentMediaCleanupJob,
)


async def media_reference_exists(
    session: AsyncSession,
    *,
    storage_key: str,
) -> bool:
    """Fail closed when a cleanup candidate is still referenced by the catalog."""

    referenced = await session.scalar(
        sa.select(
            sa.or_(
                sa.exists(
                    sa.select(1).where(
                        SpecialEquipmentCategory.image_key == storage_key
                    )
                ),
                sa.exists(
                    sa.select(1).where(
                        SpecialEquipmentProductImage.storage_key == storage_key
                    )
                ),
            )
        )
    )
    return bool(referenced)


async def claim_cleanup_jobs(
    session: AsyncSession,
    *,
    worker_id: str,
    limit: int,
    lease_seconds: int,
) -> list[dict[str, Any]]:
    """Lease due jobs without allowing two workers to delete the same object."""

    now = datetime.now(UTC)
    jobs = list(
        await session.scalars(
            sa.select(SpecialEquipmentMediaCleanupJob)
            .where(
                sa.or_(
                    sa.and_(
                        SpecialEquipmentMediaCleanupJob.status == "pending",
                        SpecialEquipmentMediaCleanupJob.next_attempt_at <= now,
                    ),
                    sa.and_(
                        SpecialEquipmentMediaCleanupJob.status == "processing",
                        SpecialEquipmentMediaCleanupJob.lease_until < now,
                    ),
                )
            )
            .order_by(
                SpecialEquipmentMediaCleanupJob.next_attempt_at,
                SpecialEquipmentMediaCleanupJob.id,
            )
            .with_for_update(skip_locked=True)
            .limit(limit)
        )
    )
    lease_until = now + timedelta(seconds=lease_seconds)
    result: list[dict[str, Any]] = []
    for job in jobs:
        job.status = "processing"
        job.attempt_count += 1
        job.lease_owner = worker_id
        job.lease_until = lease_until
        job.updated_at = now
        result.append(
            {
                "id": job.id,
                "storage_key": job.storage_key,
                "attempt_count": job.attempt_count,
            }
        )
    await session.flush()
    return result


async def mark_cleanup_completed(
    session: AsyncSession,
    *,
    job_id: UUID,
    worker_id: str,
) -> bool:
    """Acknowledge deletion only while this worker still owns the lease."""

    now = datetime.now(UTC)
    result = await session.execute(
        sa.update(SpecialEquipmentMediaCleanupJob)
        .where(
            SpecialEquipmentMediaCleanupJob.id == job_id,
            SpecialEquipmentMediaCleanupJob.status == "processing",
            SpecialEquipmentMediaCleanupJob.lease_owner == worker_id,
        )
        .values(
            status="completed",
            lease_owner=None,
            lease_until=None,
            last_error=None,
            completed_at=now,
            updated_at=now,
        )
    )
    return bool(getattr(result, "rowcount", 0))


async def mark_cleanup_failed(
    session: AsyncSession,
    *,
    job_id: UUID,
    worker_id: str,
    error_code: str,
    retry_at: datetime,
    max_attempts: int,
) -> str | None:
    """Release a failed lease for retry, or terminally fail exhausted work."""

    job = await session.scalar(
        sa.select(SpecialEquipmentMediaCleanupJob)
        .where(
            SpecialEquipmentMediaCleanupJob.id == job_id,
            SpecialEquipmentMediaCleanupJob.status == "processing",
            SpecialEquipmentMediaCleanupJob.lease_owner == worker_id,
        )
        .with_for_update()
    )
    if job is None:
        return None
    now = datetime.now(UTC)
    job.status = "failed" if job.attempt_count >= max_attempts else "pending"
    job.next_attempt_at = retry_at
    job.lease_owner = None
    job.lease_until = None
    job.last_error = error_code[:1000]
    job.updated_at = now
    await session.flush()
    return job.status
