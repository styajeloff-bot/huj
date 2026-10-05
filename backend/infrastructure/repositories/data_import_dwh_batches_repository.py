"""Persistence for durable DWH batches produced by CSV imports."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, TypedDict, cast

from sqlalchemy import and_, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.models.import_jobs import DataImportDwhBatch
from infrastructure.repository_timing import timed_repository


class DwhBatchRecord(TypedDict):
    id: uuid.UUID
    job_id: uuid.UUID
    payloads: dict[str, list[dict[str, Any]]]
    rows_count: int
    row_errors: list[str]
    status: str
    attempts: int
    next_attempt_at: datetime | None
    locked_at: datetime | None
    last_error: str | None


class DwhBatchCreateResult(TypedDict):
    id: uuid.UUID
    created: bool


class DwhBatchTransition(TypedDict):
    job_id: uuid.UUID
    rows_count: int
    row_errors: list[str]


class DwhBatchFailure(TypedDict):
    job_id: uuid.UUID
    attempts: int
    exhausted: bool


def _now() -> datetime:
    return datetime.now(UTC)


def _as_record(batch: DataImportDwhBatch) -> DwhBatchRecord:
    return {
        "id": batch.id,
        "job_id": batch.job_id,
        "payloads": batch.payloads,
        "rows_count": batch.rows_count,
        "row_errors": batch.row_errors,
        "status": batch.status,
        "attempts": batch.attempts,
        "next_attempt_at": batch.next_attempt_at,
        "locked_at": batch.locked_at,
        "last_error": batch.last_error,
    }


def _claimable(now: datetime, stale_before: datetime) -> Any:
    return or_(
        and_(
            DataImportDwhBatch.status == "pending",
            or_(
                DataImportDwhBatch.next_attempt_at.is_(None),
                DataImportDwhBatch.next_attempt_at <= now,
            ),
        ),
        and_(
            DataImportDwhBatch.status == "publishing",
            or_(
                DataImportDwhBatch.locked_at.is_(None),
                DataImportDwhBatch.locked_at <= stale_before,
            ),
        ),
    )


class DataImportDwhBatchesRepository:
    """Claims and transitions import-scoped DWH batches."""

    @staticmethod
    @timed_repository
    async def create(
        session: AsyncSession,
        *,
        batch_id: uuid.UUID,
        job_id: uuid.UUID,
        payloads: dict[str, list[dict[str, Any]]],
        rows_count: int,
        row_errors: list[str],
    ) -> DwhBatchCreateResult:
        result = await session.execute(
            insert(DataImportDwhBatch)
            .values(
                id=batch_id,
                job_id=job_id,
                payloads=payloads,
                rows_count=rows_count,
                row_errors=row_errors,
                status="pending",
                attempts=0,
            )
            .on_conflict_do_nothing(index_elements=[DataImportDwhBatch.id])
            .returning(DataImportDwhBatch.id)
        )
        created_id = result.scalar_one_or_none()
        return {
            "id": batch_id,
            "created": created_id is not None,
        }

    @staticmethod
    @timed_repository
    async def get(
        session: AsyncSession, batch_id: uuid.UUID
    ) -> DwhBatchRecord | None:
        result = await session.execute(
            select(DataImportDwhBatch).where(DataImportDwhBatch.id == batch_id)
        )
        batch = result.scalar_one_or_none()
        return _as_record(batch) if batch is not None else None

    @staticmethod
    @timed_repository
    async def claim_by_id(
        session: AsyncSession,
        batch_id: uuid.UUID,
        *,
        stale_after: timedelta,
    ) -> DwhBatchRecord | None:
        now = _now()
        stale_before = now - stale_after
        result = await session.execute(
            update(DataImportDwhBatch)
            .where(
                DataImportDwhBatch.id == batch_id,
                _claimable(now, stale_before),
            )
            .values(
                status="publishing",
                attempts=DataImportDwhBatch.attempts + 1,
                locked_at=now,
                next_attempt_at=None,
            )
            .returning(DataImportDwhBatch)
        )
        batch = result.scalar_one_or_none()
        return _as_record(batch) if batch is not None else None

    @staticmethod
    @timed_repository
    async def claim_due(
        session: AsyncSession,
        *,
        limit: int,
        stale_after: timedelta,
    ) -> list[DwhBatchRecord]:
        now = _now()
        stale_before = now - stale_after
        result = await session.execute(
            select(DataImportDwhBatch)
            .where(_claimable(now, stale_before))
            .order_by(DataImportDwhBatch.created_at.asc())
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        batches = list(result.scalars().all())
        for batch in batches:
            batch.status = "publishing"
            batch.attempts += 1
            batch.locked_at = now
            batch.next_attempt_at = None
        await session.flush()
        return [_as_record(batch) for batch in batches]

    @staticmethod
    @timed_repository
    async def mark_delivered(
        session: AsyncSession, batch_id: uuid.UUID
    ) -> DwhBatchTransition | None:
        now = _now()
        result = await session.execute(
            update(DataImportDwhBatch)
            .where(
                DataImportDwhBatch.id == batch_id,
                DataImportDwhBatch.status == "publishing",
            )
            .values(
                status="delivered",
                delivered_at=now,
                locked_at=None,
                next_attempt_at=None,
                last_error=None,
            )
            .returning(
                DataImportDwhBatch.job_id,
                DataImportDwhBatch.rows_count,
                DataImportDwhBatch.row_errors,
            )
        )
        row = result.mappings().one_or_none()
        if row is None:
            return None
        return {
            "job_id": row["job_id"],
            "rows_count": row["rows_count"],
            "row_errors": row["row_errors"],
        }

    @staticmethod
    @timed_repository
    async def record_failure(
        session: AsyncSession,
        batch_id: uuid.UUID,
        *,
        error: str,
        max_attempts: int,
        retry_after: timedelta,
    ) -> DwhBatchFailure | None:
        current = await DataImportDwhBatchesRepository.get(session, batch_id)
        if current is None or current["status"] != "publishing":
            return None
        exhausted = current["attempts"] >= max_attempts
        result = await session.execute(
            update(DataImportDwhBatch)
            .where(
                DataImportDwhBatch.id == batch_id,
                DataImportDwhBatch.status == "publishing",
                DataImportDwhBatch.attempts == current["attempts"],
            )
            .values(
                status="failed" if exhausted else "pending",
                locked_at=None,
                next_attempt_at=None if exhausted else _now() + retry_after,
                last_error=error,
            )
        )
        if int(cast("CursorResult[Any]", result).rowcount or 0) == 0:
            return None
        return {
            "job_id": current["job_id"],
            "attempts": current["attempts"],
            "exhausted": exhausted,
        }
