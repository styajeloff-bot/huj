from __future__ import annotations

from datetime import timedelta
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.models.import_jobs import DataImportDwhBatch
from infrastructure.repositories.data_import_dwh_batches_repository import (
    DataImportDwhBatchesRepository,
)
from infrastructure.repositories.data_import_jobs_repository import (
    DataImportJobsRepository,
)

pytestmark = pytest.mark.asyncio


async def _create_job(session: AsyncSession, *, rows_total: int = 1) -> UUID:
    job_id = await DataImportJobsRepository.create(
        session,
        kind="applications",
        user_id=uuid4(),
        s3_key="imports/test.csv",
        filename="test.csv",
    )
    await DataImportJobsRepository.set_rows_total(session, job_id, rows_total)
    await DataImportJobsRepository.set_status(session, job_id, "ingesting")
    await session.flush()
    return cast("UUID", job_id)


async def test_batch_is_rolled_back_with_business_transaction(
    db_session: AsyncSession,
) -> None:
    job_id = await _create_job(db_session)
    transaction = await db_session.begin_nested()
    batch_id = uuid4()
    await DataImportDwhBatchesRepository.create(
        db_session,
        batch_id=batch_id,
        job_id=job_id,
        payloads={"lca.snapshot.v1": [{"id": str(uuid4())}]},
        rows_count=1,
        row_errors=[],
    )

    await transaction.rollback()

    assert await DataImportDwhBatchesRepository.get(db_session, batch_id) is None


async def test_delivered_transition_is_idempotent(
    db_session: AsyncSession,
) -> None:
    job_id = await _create_job(db_session)
    payloads: dict[str, list[dict[str, Any]]] = {
        "lca.snapshot.v1": [{"id": str(uuid4())}]
    }
    batch_id = uuid4()
    await DataImportDwhBatchesRepository.create(
        db_session,
        batch_id=batch_id,
        job_id=job_id,
        payloads=payloads,
        rows_count=1,
        row_errors=["row warning"],
    )

    claimed = await DataImportDwhBatchesRepository.claim_by_id(
        db_session, batch_id, stale_after=timedelta(minutes=5)
    )
    first = await DataImportDwhBatchesRepository.mark_delivered(db_session, batch_id)
    second = await DataImportDwhBatchesRepository.mark_delivered(db_session, batch_id)

    assert claimed is not None
    assert claimed["attempts"] == 1
    assert claimed["payloads"] == payloads
    assert first == {
        "job_id": job_id,
        "rows_count": 1,
        "row_errors": ["row warning"],
    }
    assert second is None


async def test_failure_records_retry_then_exhausts(
    db_session: AsyncSession,
) -> None:
    job_id = await _create_job(db_session)
    batch_id = uuid4()
    await DataImportDwhBatchesRepository.create(
        db_session,
        batch_id=batch_id,
        job_id=job_id,
        payloads={"topic": [{"id": "stable"}]},
        rows_count=1,
        row_errors=[],
    )
    await DataImportDwhBatchesRepository.claim_by_id(
        db_session, batch_id, stale_after=timedelta(minutes=5)
    )

    retry = await DataImportDwhBatchesRepository.record_failure(
        db_session,
        batch_id,
        error="kafka unavailable",
        max_attempts=2,
        retry_after=timedelta(seconds=-1),
    )
    await DataImportDwhBatchesRepository.claim_by_id(
        db_session, batch_id, stale_after=timedelta(minutes=5)
    )
    exhausted = await DataImportDwhBatchesRepository.record_failure(
        db_session,
        batch_id,
        error="kafka still unavailable",
        max_attempts=2,
        retry_after=timedelta(minutes=1),
    )
    stored = await DataImportDwhBatchesRepository.get(db_session, batch_id)

    assert retry == {"job_id": job_id, "attempts": 1, "exhausted": False}
    assert exhausted == {"job_id": job_id, "attempts": 2, "exhausted": True}
    assert stored is not None
    assert stored["status"] == "failed"
    assert stored["next_attempt_at"] is None
    assert stored["last_error"] == "kafka still unavailable"


async def test_claim_due_recovers_stale_publishing_batch(
    db_session: AsyncSession,
) -> None:
    job_id = await _create_job(db_session)
    batch_id = uuid4()
    await DataImportDwhBatchesRepository.create(
        db_session,
        batch_id=batch_id,
        job_id=job_id,
        payloads={},
        rows_count=1,
        row_errors=[],
    )
    first = await DataImportDwhBatchesRepository.claim_due(
        db_session, limit=10, stale_after=timedelta(minutes=5)
    )
    await db_session.execute(
        update(DataImportDwhBatch)
        .where(DataImportDwhBatch.id == batch_id)
        .values(locked_at=DataImportDwhBatch.created_at - timedelta(minutes=10))
    )
    second = await DataImportDwhBatchesRepository.claim_due(
        db_session, limit=10, stale_after=timedelta(minutes=5)
    )

    assert [batch["id"] for batch in first] == [batch_id]
    assert [batch["id"] for batch in second] == [batch_id]
    assert second[0]["attempts"] == 2


async def test_job_cannot_finalize_with_unresolved_batch(
    db_session: AsyncSession,
) -> None:
    job_id = await _create_job(db_session)
    batch_id = uuid4()
    await DataImportDwhBatchesRepository.create(
        db_session,
        batch_id=batch_id,
        job_id=job_id,
        payloads={},
        rows_count=1,
        row_errors=[],
    )
    await DataImportJobsRepository.mark_publishing(db_session, job_id)
    await DataImportJobsRepository.record_progress(
        db_session, job_id, rows_done_delta=1, new_errors=[]
    )

    assert await DataImportJobsRepository.try_finalize(db_session, job_id) is False

    await DataImportDwhBatchesRepository.claim_by_id(
        db_session, batch_id, stale_after=timedelta(minutes=5)
    )
    await DataImportDwhBatchesRepository.mark_delivered(db_session, batch_id)

    assert await DataImportJobsRepository.try_finalize(db_session, job_id) is True


async def test_create_is_idempotent_for_stable_batch_id(
    db_session: AsyncSession,
) -> None:
    job_id = await _create_job(db_session)
    batch_id = uuid4()
    first = await DataImportDwhBatchesRepository.create(
        db_session,
        batch_id=batch_id,
        job_id=job_id,
        payloads={"topic": [{"version": "first"}]},
        rows_count=1,
        row_errors=[],
    )
    second = await DataImportDwhBatchesRepository.create(
        db_session,
        batch_id=batch_id,
        job_id=job_id,
        payloads={"topic": [{"version": "duplicate"}]},
        rows_count=1,
        row_errors=["must not overwrite"],
    )
    stored = await DataImportDwhBatchesRepository.get(db_session, batch_id)

    assert first == {"id": batch_id, "created": True}
    assert second == {"id": batch_id, "created": False}
    assert stored is not None
    assert stored["payloads"] == {"topic": [{"version": "first"}]}
    assert stored["row_errors"] == []
