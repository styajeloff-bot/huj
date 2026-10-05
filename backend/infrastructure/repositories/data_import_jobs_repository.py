"""Repository for data_import_jobs — generic async CSV-import tracking."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import exists, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.models.import_jobs import DataImportDwhBatch, DataImportJob
from infrastructure.repository_timing import timed_repository

_ERROR_SAMPLE_CAP = 10


def _now() -> datetime:
    return datetime.now(UTC)


class DataImportJobsRepository:
    """Lifecycle of one CSV import (queued → ingesting → done/failed)."""

    @staticmethod
    @timed_repository
    async def create(
        session: AsyncSession,
        *,
        kind: str,
        user_id: UUID,
        s3_key: str,
        filename: str | None,
        params: dict[str, Any] | None = None,
    ) -> uuid.UUID:
        job = DataImportJob(
            kind=kind,
            user_id=user_id,
            s3_key=s3_key,
            filename=filename,
            status="queued",
            rows_total=0,
            rows_done=0,
            errors_count=0,
            error_sample=[],
            params=params or {},
        )
        session.add(job)
        await session.flush()
        return job.id

    @staticmethod
    @timed_repository
    async def get(
        session: AsyncSession, job_id: uuid.UUID
    ) -> dict[str, Any] | None:
        result = await session.execute(
            select(DataImportJob).where(DataImportJob.id == job_id)
        )
        job = result.scalar_one_or_none()
        if job is None:
            return None
        return {
            "id": job.id,
            "kind": job.kind,
            "user_id": job.user_id,
            "s3_key": job.s3_key,
            "filename": job.filename,
            "status": job.status,
            "rows_total": job.rows_total,
            "rows_done": job.rows_done,
            "errors_count": job.errors_count,
            "error_sample": job.error_sample or [],
            "params": job.params or {},
            "error": job.error,
            "created_at": job.created_at,
            "updated_at": job.updated_at,
        }

    @staticmethod
    @timed_repository
    async def set_status(
        session: AsyncSession,
        job_id: uuid.UUID,
        status: str,
        *,
        error: str | None = None,
    ) -> None:
        values: dict[str, Any] = {"status": status, "updated_at": _now()}
        if error is not None:
            values["error"] = error
        await session.execute(
            update(DataImportJob).where(DataImportJob.id == job_id).values(**values)
        )

    @staticmethod
    @timed_repository
    async def set_rows_total(
        session: AsyncSession, job_id: uuid.UUID, rows_total: int
    ) -> None:
        await session.execute(
            update(DataImportJob)
            .where(DataImportJob.id == job_id)
            .values(rows_total=rows_total, updated_at=_now())
        )

    @staticmethod
    @timed_repository
    async def record_progress(
        session: AsyncSession,
        job_id: uuid.UUID,
        *,
        rows_done_delta: int,
        new_errors: list[str],
    ) -> None:
        """Increment processed rows and append (capped) error samples."""
        result = await session.execute(
            select(DataImportJob.error_sample, DataImportJob.errors_count).where(
                DataImportJob.id == job_id
            )
        )
        row = result.first()
        sample: list[str] = list(row[0] or []) if row else []
        if new_errors:
            room = _ERROR_SAMPLE_CAP - len(sample)
            if room > 0:
                sample.extend(new_errors[:room])
        values: dict[str, Any] = {
            "rows_done": DataImportJob.rows_done + rows_done_delta,
            "updated_at": _now(),
        }
        if new_errors:
            values["errors_count"] = DataImportJob.errors_count + len(new_errors)
            values["error_sample"] = sample
        await session.execute(
            update(DataImportJob).where(DataImportJob.id == job_id).values(**values)
        )

    @staticmethod
    @timed_repository
    async def mark_publishing(session: AsyncSession, job_id: uuid.UUID) -> None:
        """Expose the post-ingestion delivery phase without reviving terminal jobs."""
        await session.execute(
            update(DataImportJob)
            .where(
                DataImportJob.id == job_id,
                DataImportJob.status.in_(("ingesting", "publishing")),
            )
            .values(status="publishing", updated_at=_now())
        )

    @staticmethod
    @timed_repository
    async def try_finalize(session: AsyncSession, job_id: uuid.UUID) -> bool:
        """Move an active job to ``done`` only after every DWH batch delivered."""
        unresolved_batch = exists(
            select(DataImportDwhBatch.id).where(
                DataImportDwhBatch.job_id == job_id,
                DataImportDwhBatch.status != "delivered",
            )
        )
        result = await session.execute(
            update(DataImportJob)
            .where(
                DataImportJob.id == job_id,
                DataImportJob.status.in_(("ingesting", "publishing")),
                DataImportJob.rows_done >= DataImportJob.rows_total,
                ~unresolved_batch,
            )
            .values(status="done", updated_at=_now())
        )
        return bool(result.rowcount)  # type: ignore[attr-defined]
