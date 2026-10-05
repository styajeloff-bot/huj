"""Repository for catalog_import_jobs — job tracking for catalog uploads."""
from __future__ import annotations

import uuid
from typing import Any, cast
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.models.catalog_import_jobs import CatalogImportJob
from infrastructure.repository_timing import timed_repository


def _rowcount(result: object) -> int:
    return int(cast("CursorResult[Any]", result).rowcount or 0)


class CatalogImportJobsRepository:
    """Tracks the lifecycle of one catalog upload (queued → done/failed)."""

    @staticmethod
    @timed_repository
    async def create(
        session: AsyncSession,
        *,
        user_id: UUID,
        s3_key: str,
        filename: str | None,
    ) -> uuid.UUID:
        job = CatalogImportJob(
            user_id=user_id,
            s3_key=s3_key,
            filename=filename,
            status="queued",
            rows_total=0,
            rows_done=0,
            images_total=0,
            images_done=0,
            images_failed=0,
        )
        session.add(job)
        await session.flush()
        return job.id

    @staticmethod
    @timed_repository
    async def get(
        session: AsyncSession, job_id: uuid.UUID
    ) -> dict[str, Any] | None:
        stmt = select(CatalogImportJob).where(CatalogImportJob.id == job_id)
        result = await session.execute(stmt)
        job = result.scalar_one_or_none()
        if job is None:
            return None
        return {
            "id": job.id,
            "user_id": job.user_id,
            "s3_key": job.s3_key,
            "filename": job.filename,
            "status": job.status,
            "rows_total": job.rows_total,
            "rows_done": job.rows_done,
            "images_total": job.images_total,
            "images_done": job.images_done,
            "images_failed": job.images_failed,
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
            update(CatalogImportJob)
            .where(CatalogImportJob.id == job_id)
            .values(**values)
        )

    @staticmethod
    @timed_repository
    async def set_totals(
        session: AsyncSession,
        job_id: uuid.UUID,
        *,
        rows_total: int | None = None,
        images_total_delta: int | None = None,
    ) -> None:
        values: dict[str, Any] = {"updated_at": _now()}
        if rows_total is not None:
            values["rows_total"] = rows_total
            values["rows_done"] = 0
            values["images_total"] = 0
            values["images_done"] = 0
            values["images_failed"] = 0
            values["error"] = None
        stmt = (
            update(CatalogImportJob)
            .where(CatalogImportJob.id == job_id)
            .values(**values)
        )
        if images_total_delta:
            stmt = stmt.values(
                images_total=CatalogImportJob.images_total + images_total_delta
            )
        await session.execute(stmt)

    @staticmethod
    @timed_repository
    async def increment_rows_done(
        session: AsyncSession, job_id: uuid.UUID, delta: int
    ) -> None:
        await session.execute(
            update(CatalogImportJob)
            .where(CatalogImportJob.id == job_id)
            .values(
                rows_done=CatalogImportJob.rows_done + delta,
                updated_at=_now(),
            )
        )

    @staticmethod
    @timed_repository
    async def increment_images_done(
        session: AsyncSession, job_id: uuid.UUID, delta: int
    ) -> None:
        await session.execute(
            update(CatalogImportJob)
            .where(CatalogImportJob.id == job_id)
            .values(
                images_done=CatalogImportJob.images_done + delta,
                updated_at=_now(),
            )
        )

    @staticmethod
    @timed_repository
    async def increment_images_failed(
        session: AsyncSession, job_id: uuid.UUID, delta: int
    ) -> None:
        await session.execute(
            update(CatalogImportJob)
            .where(CatalogImportJob.id == job_id)
            .values(
                images_failed=CatalogImportJob.images_failed + delta,
                updated_at=_now(),
            )
        )

    @staticmethod
    @timed_repository
    async def try_finalize(
        session: AsyncSession, job_id: uuid.UUID
    ) -> bool:
        """Atomically move job to ``done`` if all row counters are satisfied.

        Conditions (enforced in SQL WHERE clause):
        - ``status = 'ingesting'``
        - ``rows_total > 0`` (rows have been counted)
        - ``rows_done >= rows_total`` (all rows processed)

        Only one concurrent caller can transition the row (``UPDATE ...
        WHERE`` is atomic within a single statement); the others see
        ``rowcount = 0`` and return ``False``.
        """
        result = await session.execute(
            update(CatalogImportJob)
            .where(
                CatalogImportJob.id == job_id,
                CatalogImportJob.status == "ingesting",
                CatalogImportJob.rows_total > 0,
                CatalogImportJob.rows_done >= CatalogImportJob.rows_total,
            )
            .values(status="done", updated_at=_now())
        )
        return bool(_rowcount(result))

    @staticmethod
    @timed_repository
    async def list_recoverable(
        session: AsyncSession,
    ) -> list[dict[str, Any]]:
        """Return catalog jobs that should be re-enqueued after worker restart."""
        stmt = (
            select(
                CatalogImportJob.id,
                CatalogImportJob.s3_key,
                CatalogImportJob.filename,
                CatalogImportJob.status,
            )
            .where(CatalogImportJob.status.in_(("queued", "parsing", "ingesting")))
            .order_by(CatalogImportJob.created_at.asc())
        )
        result = await session.execute(stmt)
        return [dict(row) for row in result.mappings().all()]

def _now() -> Any:
    from datetime import UTC, datetime

    return datetime.now(UTC)
