"""Generic CSV-import upload command — store to object storage + enqueue task.

Tiny by design (like ``catalog`` upload): persist the raw CSV, create a
``data_import_jobs`` row, enqueue ONE ``data_import.process_upload`` task, and
return ``202 {job_id}``. All heavy work happens in the taskiq worker.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.errors import ServiceError
from application.tasks.data_import import process_upload
from infrastructure.repositories.data_import_jobs_repository import (
    DataImportJobsRepository,
)
from infrastructure.services.object_storage import get_object_storage

logger = logging.getLogger("carcraft-backend")

_CSV_CONTENT_TYPE = "text/csv"


@dataclass
class UploadDataImportCommand:
    kind: str
    file_bytes: bytes
    filename: str | None
    user_id: UUID
    params: dict[str, Any] = field(default_factory=dict)


async def handle_upload_data_import(
    cmd: UploadDataImportCommand, session: AsyncSession
) -> dict[str, Any]:
    if not cmd.file_bytes:
        raise ServiceError("Пустой файл", status_code=400)

    s3_key = f"uploads/data-import/{cmd.kind}/{uuid.uuid4().hex}.csv"
    storage = get_object_storage()
    try:
        await storage.put(s3_key, cmd.file_bytes, _CSV_CONTENT_TYPE)
    except Exception as exc:
        logger.error("data_import_s3_put_failed kind=%s err=%s", cmd.kind, exc)
        raise ServiceError("Не удалось сохранить файл", status_code=502) from exc

    job_id = await DataImportJobsRepository.create(
        session,
        kind=cmd.kind,
        user_id=cmd.user_id,
        s3_key=s3_key,
        filename=cmd.filename,
        params=cmd.params,
    )
    await session.commit()

    try:
        await process_upload.kiq(
            job_id=str(job_id),
            s3_key=s3_key,
            kind=cmd.kind,
            params=cmd.params,
        )
    except Exception as exc:
        logger.error("data_import_enqueue_failed job=%s err=%s", job_id, exc)
        await DataImportJobsRepository.set_status(
            session, job_id, "failed", error=f"enqueue failed: {exc}"
        )
        await session.commit()
        raise ServiceError("Не удалось поставить задачу в очередь", status_code=502) from exc

    logger.info("data_import_enqueued job=%s kind=%s", job_id, cmd.kind)
    return {"job_id": str(job_id), "status": "queued"}
