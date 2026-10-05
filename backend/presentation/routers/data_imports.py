"""Async CSV-import endpoints (carcraft_employee) + progress polling.

Each upload stores the CSV, enqueues a Taskiq job, and returns ``202 {jobId}``.
Progress is polled via ``GET /api/v1/imports/{job_id}``. Heavy processing runs
in the taskiq-worker (see ``application/tasks/data_import.py``).
"""
from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from application.commands.data_import import (
    UploadDataImportCommand,
    handle_upload_data_import,
)
from application.errors import ServiceError
from application.queries.data_import import get_import_job_status
from infrastructure.database import get_db
from presentation.dependencies.auth import require_roles

router = APIRouter(tags=["data-imports"])

_employee_only = require_roles("carcraft_employee")


class ImportEnqueuedResponse(BaseModel):
    job_id: str
    status: str


class ImportJobStatus(BaseModel):
    id: str
    kind: str
    filename: str | None = None
    status: str
    rows_total: int
    rows_done: int
    errors_count: int
    error_sample: list[str] = Field(default_factory=list)
    error: str | None = None


def _http(exc: ServiceError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=str(exc))


async def _enqueue(
    *,
    kind: str,
    file: UploadFile,
    user: dict[str, Any],
    session: AsyncSession,
    params: dict[str, Any] | None = None,
) -> ImportEnqueuedResponse:
    if file.filename and not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=422, detail="Ожидается CSV-файл")
    file_bytes = await file.read()
    try:
        result = await handle_upload_data_import(
            UploadDataImportCommand(
                kind=kind,
                file_bytes=file_bytes,
                filename=file.filename,
                user_id=user["id"],
                params=params or {},
            ),
            session,
        )
    except ServiceError as exc:
        raise _http(exc) from exc
    return ImportEnqueuedResponse(job_id=result["job_id"], status=result["status"])


@router.post(
    "/api/v1/vehicles/import",
    response_model=ImportEnqueuedResponse,
    status_code=202,
    summary="[admin] Импорт ТС (склад) из CSV — асинхронно",
)
async def import_vehicles(
    user: Annotated[dict, Depends(_employee_only)],
    session: Annotated[AsyncSession, Depends(get_db)],
    file: Annotated[UploadFile, File(...)],
) -> ImportEnqueuedResponse:
    return await _enqueue(kind="vehicles", file=file, user=user, session=session)


@router.post(
    "/api/v1/warehouses/import",
    response_model=ImportEnqueuedResponse,
    status_code=202,
    summary="[admin] Импорт складов из CSV — асинхронно",
)
async def import_warehouses(
    user: Annotated[dict, Depends(_employee_only)],
    session: Annotated[AsyncSession, Depends(get_db)],
    file: Annotated[UploadFile, File(...)],
) -> ImportEnqueuedResponse:
    return await _enqueue(kind="warehouses", file=file, user=user, session=session)


@router.post(
    "/api/v1/exchange/requests/import",
    response_model=ImportEnqueuedResponse,
    status_code=202,
    summary="[admin] Импорт запросов биржи из CSV — асинхронно",
)
async def import_exchange_requests(
    user: Annotated[dict, Depends(_employee_only)],
    session: Annotated[AsyncSession, Depends(get_db)],
    file: Annotated[UploadFile, File(...)],
) -> ImportEnqueuedResponse:
    return await _enqueue(
        kind="exchange_requests", file=file, user=user, session=session
    )


@router.post(
    "/api/v1/exchange/bids/import",
    response_model=ImportEnqueuedResponse,
    status_code=202,
    summary="[admin] Импорт ставок биржи из CSV — асинхронно",
)
async def import_exchange_bids(
    user: Annotated[dict, Depends(_employee_only)],
    session: Annotated[AsyncSession, Depends(get_db)],
    file: Annotated[UploadFile, File(...)],
) -> ImportEnqueuedResponse:
    return await _enqueue(kind="exchange_bids", file=file, user=user, session=session)


@router.post(
    "/api/v1/admin/companies/distributor-dealer-links/import",
    response_model=ImportEnqueuedResponse,
    status_code=202,
    summary="[admin] Импорт связей дистрибьютор↔дилер из CSV — асинхронно",
)
async def import_distributor_dealer_links(
    user: Annotated[dict, Depends(_employee_only)],
    session: Annotated[AsyncSession, Depends(get_db)],
    file: Annotated[UploadFile, File(...)],
) -> ImportEnqueuedResponse:
    return await _enqueue(
        kind="distributor_dealer_links", file=file, user=user, session=session
    )


@router.get(
    "/api/v1/imports/{job_id}",
    response_model=ImportJobStatus,
    dependencies=[Depends(_employee_only)],
    summary="[admin] Статус задачи импорта",
)
async def get_import_status(
    session: Annotated[AsyncSession, Depends(get_db)],
    job_id: UUID,
) -> ImportJobStatus:
    job = await get_import_job_status(session, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Задача импорта не найдена")
    return ImportJobStatus(
        id=str(job["id"]),
        kind=job["kind"],
        filename=job["filename"],
        status=job["status"],
        rows_total=job["rows_total"],
        rows_done=job["rows_done"],
        errors_count=job["errors_count"],
        error_sample=job["error_sample"],
        error=job["error"],
    )
