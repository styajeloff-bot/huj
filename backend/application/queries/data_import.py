"""Query: data-import job status (for GET /api/v1/imports/{job_id})."""
from __future__ import annotations

from typing import Any, cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.repositories.data_import_jobs_repository import (
    DataImportJobsRepository,
)


async def get_import_job_status(
    session: AsyncSession, job_id: UUID
) -> dict[str, Any] | None:
    """Return the job-status dict, or None if the job does not exist."""
    job = await DataImportJobsRepository.get(session, job_id)
    return cast("dict[str, Any] | None", job)
