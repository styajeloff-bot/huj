"""Catalog preview + import-job status queries."""
from __future__ import annotations

import asyncio
import io
import uuid
from typing import Any, BinaryIO

from sqlalchemy.ext.asyncio import AsyncSession

from application.errors import ServiceError
from infrastructure.repositories.catalog_import_jobs_repository import (
    CatalogImportJobsRepository,
)
from infrastructure.services.catalog_parser import parse_excel_preview


async def handle_catalog_preview(
    source: bytes | io.BytesIO | BinaryIO,
) -> dict[str, Any]:
    """Parse an uploaded Excel file and return preview statistics.

    Parsing is CPU-bound (pandas/openpyxl); run it in a worker thread so the
    event loop stays responsive.
    """
    try:
        result = await asyncio.to_thread(parse_excel_preview, source)
    except ValueError as exc:
        raise ServiceError(str(exc), status_code=400) from exc
    return dict(result)


async def handle_get_catalog_job_status(
    session: AsyncSession, job_id: str
) -> dict[str, Any]:
    """Return progress for a single catalog upload job."""
    try:
        parsed_id = uuid.UUID(job_id)
    except ValueError as exc:
        raise ServiceError("Некорректный jobId", status_code=400) from exc

    job = await CatalogImportJobsRepository.get(session, parsed_id)
    if job is None:
        raise ServiceError("Задача не найдена", status_code=404)

    return {
        "job_id": str(job["id"]),
        "status": job["status"],
        "rows_total": job["rows_total"],
        "rows_done": job["rows_done"],
        "images_total": job["images_total"],
        "images_done": job["images_done"],
        "images_failed": job["images_failed"],
        "error": job["error"],
        "filename": job["filename"],
        "created_at": job["created_at"].isoformat(),
        "updated_at": job["updated_at"].isoformat(),
    }
