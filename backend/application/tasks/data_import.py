"""Taskiq tasks for the async CSV data-import pipeline.

Flow (mirrors ``catalog.py``):

    data_import.process_upload      → download CSV from object storage, parse,
                                      fan out row batches
    data_import.process_rows_batch  → upsert one batch into PostgreSQL +
                                      persist a durable DWH delivery batch

All upserts are idempotent (ON CONFLICT), so a retried/restarted task is safe.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass
from typing import Any, NoReturn

from application.services.data_import import (
    NATIVE_KINDS,
    BatchResult,
    parse_csv,
    process_batch,
)
from application.tasks.dwh_batches import deliver_dwh_batch
from infrastructure.database import AsyncSessionLocal, get_pool_status
from infrastructure.messaging.dwh_events import serialise_dwh_value
from infrastructure.metrics import DWH_DURABLE_BATCHES
from infrastructure.repositories.data_import_dwh_batches_repository import (
    DataImportDwhBatchesRepository,
)
from infrastructure.repositories.data_import_jobs_repository import (
    DataImportJobsRepository,
)
from infrastructure.services.object_storage import get_object_storage
from infrastructure.settings import settings
from infrastructure.taskiq_broker import broker

logger = logging.getLogger("carcraft-backend")

BATCH_SIZE = 500


@dataclass
class _ImportSemaphoreState:
    semaphore: asyncio.Semaphore | None = None
    limit: int | None = None


_import_semaphore_state = _ImportSemaphoreState()


class _RowLogicalError(Exception):
    """Internal signal to roll back the current row savepoint."""


def _raise_row_logical_error(message: str) -> NoReturn:
    raise _RowLogicalError(message)


def _get_import_semaphore() -> asyncio.Semaphore:
    limit = max(1, settings.taskiq_import_concurrency)
    if (
        _import_semaphore_state.semaphore is None
        or _import_semaphore_state.limit != limit
    ):
        _import_semaphore_state.semaphore = asyncio.Semaphore(limit)
        _import_semaphore_state.limit = limit
    return _import_semaphore_state.semaphore


def _durable_batch_id(job_id: uuid.UUID, kind: str, offset: int) -> uuid.UUID:
    """Return the stable identity of one logical CSV batch."""
    return uuid.uuid5(job_id, f"{kind}:{offset}")


@broker.task(task_name="data_import.process_upload")
async def process_upload(
    job_id: str,
    s3_key: str,
    kind: str,
    params: dict[str, Any] | None = None,
) -> None:
    """Download the CSV, parse it, and fan out row batches."""
    job_uuid = uuid.UUID(job_id)
    storage = get_object_storage()

    async with AsyncSessionLocal() as session:
        await DataImportJobsRepository.set_status(session, job_uuid, "parsing")
        await session.commit()

    try:
        stored = await storage.get(s3_key)
    except Exception as exc:
        logger.error("data_import_s3_get_failed job=%s err=%s", job_id, exc)
        await _fail(job_uuid, f"s3 get failed: {exc}")
        return
    if stored is None or not stored.data:
        await _fail(job_uuid, "file not found in storage")
        return

    try:
        rows = parse_csv(stored.data)
    except Exception as exc:
        logger.error("data_import_parse_failed job=%s err=%s", job_id, exc)
        await _fail(job_uuid, f"parse failed: {exc}")
        return

    async with AsyncSessionLocal() as session:
        await DataImportJobsRepository.set_rows_total(session, job_uuid, len(rows))
        await DataImportJobsRepository.set_status(session, job_uuid, "ingesting")
        await session.commit()

    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i : i + BATCH_SIZE]
        try:
            await process_rows_batch.kiq(
                job_id=job_id,
                batch_id=str(_durable_batch_id(job_uuid, kind, i)),
                kind=kind,
                rows=batch,
                params=params,
            )
        except Exception as exc:
            logger.error("data_import_kiq_failed job=%s offset=%d err=%s", job_id, i, exc)

    logger.info("data_import_fanout_done job=%s kind=%s rows=%d", job_id, kind, len(rows))

    if not rows:
        async with AsyncSessionLocal() as session:
            await DataImportJobsRepository.try_finalize(session, job_uuid)
            await session.commit()


@broker.task(task_name="data_import.process_rows_batch")
async def process_rows_batch(
    job_id: str,
    batch_id: str,
    kind: str,
    rows: list[dict[str, Any]],
    params: dict[str, Any] | None = None,
) -> None:
    """Commit business rows and their durable DWH batch atomically."""
    if not rows:
        return
    job_uuid = uuid.UUID(job_id)
    durable_batch_id = uuid.UUID(batch_id)
    params = params or {}
    errors: list[str] = []
    dwh_payloads: dict[str, list[dict[str, Any]]] = {}
    async with _get_import_semaphore():
        logger.info(
            "data_import_batch_start job=%s kind=%s rows=%d pool=%s",
            job_id,
            kind,
            len(rows),
            get_pool_status(),
        )
        async with AsyncSessionLocal() as session:
            try:
                if kind in NATIVE_KINDS:
                    result = await process_batch(session, kind, rows)
                    errors = result.errors
                    dwh_payloads = result.dwh_payloads
                elif kind == "applications":
                    result = await _process_applications(session, rows, params)
                    errors = result.errors
                    dwh_payloads = result.dwh_payloads
                elif kind == "users":
                    errors = await _process_users(session, rows)
                elif kind == "companies":
                    errors = await _process_companies(session, rows, params)
                else:
                    errors = [f"unsupported import kind: {kind}"]
                durable_batch = await DataImportDwhBatchesRepository.create(
                    session,
                    batch_id=durable_batch_id,
                    job_id=job_uuid,
                    payloads=serialise_dwh_value(dwh_payloads),
                    rows_count=len(rows),
                    row_errors=errors,
                )
                await DataImportJobsRepository.mark_publishing(session, job_uuid)
                await session.commit()
            except Exception:
                await session.rollback()
                raise
        logger.info(
            "data_import_batch_done job=%s kind=%s rows=%d errors=%d pool=%s",
            job_id,
            kind,
            len(rows),
            len(errors),
            get_pool_status(),
        )
    DWH_DURABLE_BATCHES.labels(
        result="created" if durable_batch["created"] else "duplicate"
    ).inc()

    try:
        await deliver_dwh_batch.kiq(batch_id=str(durable_batch_id))
    except Exception as exc:
        # Delivery is recoverable from PostgreSQL by startup/minute reconciliation.
        logger.warning(
            "data_import_dwh_delivery_enqueue_failed batch=%s err=%s",
            durable_batch_id,
            exc,
        )


async def _process_applications(
    session: Any, rows: list[dict[str, Any]], params: dict[str, Any]
) -> BatchResult:
    """Reuse the existing application-layer LCA upsert per row."""
    from application.commands.admin_applications.import_applications import (
        _upsert_lca_row,
    )

    _ = params
    result = BatchResult()
    for idx, row in enumerate(rows, start=1):
        try:
            async with session.begin_nested():
                row_result = await _upsert_lca_row(
                    session,
                    row,
                )
                if row_result.action == "error" and row_result.error:
                    _raise_row_logical_error(row_result.error)
            for topic, payloads in row_result.dwh_payloads.items():
                for payload in payloads:
                    result.add_payload(topic, payload)
            if row_result.action in {"created", "updated"}:
                result.processed += 1
        except _RowLogicalError as exc:
            result.errors.append(f"Строка {idx}: {exc}")
        except Exception as exc:
            result.errors.append(f"Строка {idx}: {exc}")
    return result


async def _process_users(session: Any, rows: list[dict[str, Any]]) -> list[str]:
    """Reuse the application-layer per-row user upsert."""
    from application.commands.admin_users.import_rows import upsert_user_row

    errors: list[str] = []
    for idx, row in enumerate(rows, start=1):
        try:
            async with session.begin_nested():
                action, err = await upsert_user_row(session, row)
                if action == "error" and err:
                    _raise_row_logical_error(err)
        except _RowLogicalError as exc:
            errors.append(f"Строка {idx}: {exc}")
        except Exception as exc:
            errors.append(f"Строка {idx}: {exc}")
    return errors


async def _process_companies(
    session: Any, rows: list[dict[str, Any]], params: dict[str, Any]
) -> list[str]:
    """Reuse the application-layer per-row company upsert."""
    from uuid import UUID

    from application.commands.companies.import_rows import upsert_company_row

    actor_raw = params.get("actor_id")
    if not actor_raw:
        return [f"Строка {i}: отсутствует actor_id" for i in range(1, len(rows) + 1)]
    actor_id = UUID(actor_raw)
    actor_role = params.get("actor_role", "carcraft_employee")
    errors: list[str] = []
    for idx, row in enumerate(rows, start=1):
        try:
            async with session.begin_nested():
                action, err = await upsert_company_row(
                    session, actor_id=actor_id, actor_role=actor_role, row=row
                )
                if action == "error" and err:
                    _raise_row_logical_error(err)
        except _RowLogicalError as exc:
            errors.append(f"Строка {idx}: {exc}")
        except Exception as exc:
            errors.append(f"Строка {idx}: {exc}")
    return errors


async def _fail(job_uuid: uuid.UUID, error: str) -> None:
    async with AsyncSessionLocal() as session:
        await DataImportJobsRepository.set_status(
            session, job_uuid, "failed", error=error
        )
        await session.commit()
