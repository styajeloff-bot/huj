"""Durability tests for registry media deletion."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from application.tasks.special_equipment_registry import retry_delay_seconds
from infrastructure.models.special_equipment import SpecialEquipmentCategory
from infrastructure.models.special_equipment_registry import (
    SpecialEquipmentMediaCleanupJob,
)
from infrastructure.repositories import (
    special_equipment_media_cleanup_repository as repo,
)


def test_registry_media_cleanup_backoff_is_bounded() -> None:
    assert retry_delay_seconds(1) == 30
    assert retry_delay_seconds(2) == 60
    assert retry_delay_seconds(8) == 3600
    assert retry_delay_seconds(100) == 3600


@pytest.mark.asyncio
async def test_registry_media_cleanup_rechecks_live_catalog_references(
    db_session: AsyncSession,
) -> None:
    storage_key = "special-equipment/registry/categories/live.webp"
    category = SpecialEquipmentCategory(
        code="referenced-media-category",
        name="Referenced media category",
        slug="referenced-media-category",
        usage_metric="engine_hours",
        image_key=storage_key,
    )
    db_session.add(category)
    await db_session.flush()

    assert await repo.media_reference_exists(
        db_session,
        storage_key=storage_key,
    )

    category.image_key = None
    await db_session.flush()
    assert not await repo.media_reference_exists(
        db_session,
        storage_key=storage_key,
    )


@pytest.mark.asyncio
async def test_registry_media_cleanup_lease_retry_and_completion(
    db_session: AsyncSession,
) -> None:
    job = SpecialEquipmentMediaCleanupJob(
        storage_key="special-equipment/registry/test-object.webp",
        # This test exercises a due job, independently of DB/host clock skew.
        next_attempt_at=datetime.now(UTC) - timedelta(seconds=1),
    )
    db_session.add(job)
    await db_session.flush()

    first = await repo.claim_cleanup_jobs(
        db_session,
        worker_id="worker-one",
        limit=10,
        lease_seconds=300,
    )
    assert first == [
        {
            "id": job.id,
            "storage_key": job.storage_key,
            "attempt_count": 1,
        }
    ]
    assert await repo.claim_cleanup_jobs(
        db_session,
        worker_id="worker-two",
        limit=10,
        lease_seconds=300,
    ) == []

    status = await repo.mark_cleanup_failed(
        db_session,
        job_id=job.id,
        worker_id="worker-one",
        error_code="TransientStorageError",
        retry_at=datetime.now(UTC) - timedelta(seconds=1),
        max_attempts=8,
    )
    assert status == "pending"

    second = await repo.claim_cleanup_jobs(
        db_session,
        worker_id="worker-two",
        limit=10,
        lease_seconds=300,
    )
    assert second[0]["attempt_count"] == 2
    assert await repo.mark_cleanup_completed(
        db_session,
        job_id=job.id,
        worker_id="worker-one",
    ) is False
    assert await repo.mark_cleanup_completed(
        db_session,
        job_id=job.id,
        worker_id="worker-two",
    ) is True

    await db_session.refresh(job)
    assert job.status == "completed"
    assert job.attempt_count == 2
    assert job.completed_at is not None
    assert job.lease_owner is None
    assert job.lease_until is None


@pytest.mark.asyncio
async def test_registry_media_cleanup_stops_after_max_attempts(
    db_session: AsyncSession,
) -> None:
    job = SpecialEquipmentMediaCleanupJob(
        storage_key="special-equipment/registry/exhausted-object.webp",
        next_attempt_at=datetime.now(UTC) - timedelta(seconds=1),
        attempt_count=7,
    )
    db_session.add(job)
    await db_session.flush()
    claimed = await repo.claim_cleanup_jobs(
        db_session,
        worker_id="worker-final",
        limit=1,
        lease_seconds=300,
    )
    assert claimed[0]["attempt_count"] == 8

    status = await repo.mark_cleanup_failed(
        db_session,
        job_id=job.id,
        worker_id="worker-final",
        error_code="PermanentStorageError",
        retry_at=datetime.now(UTC),
        max_attempts=8,
    )
    assert status == "failed"
    await db_session.refresh(job)
    assert job.status == "failed"
    assert job.last_error == "PermanentStorageError"
