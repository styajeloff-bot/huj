"""Fire-and-forget passport recognition task.

Owns the post-upload recognition call: hash the file → look at the recognition
cache → if missing, call the recognition provider → save back to the cache →
optionally flip the document's review status to ``approved`` when the
document_type is ``auto_approve=True`` and recognition succeeded.

Failures are logged but never propagated — the upload itself is already
complete by the time this task runs.

The task takes a session-factory callable so it can open an isolated DB
session per execution; reusing the request session would race with the
outer commit lifecycle.
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.services.passport_profile_fields import (
    PASSPORT_MAIN_TYPE,
    PASSPORT_REGISTRATION_TYPE,
    profile_autofill_from_passport_records,
)
from domain.entities.document import STATUS_APPROVED
from infrastructure.repositories import (
    client_repository as client_repo,
)
from infrastructure.repositories import (
    documents_repository as docs_repo,
)
from infrastructure.repositories import (
    passport_recognition_repository as cache_repo,
)
from infrastructure.repositories import (
    status_history_repository as hist_repo,
)
from infrastructure.services.document_recognition import (
    DocumentRecognitionError,
    PassportPage,
    RecognitionResult,
    calculate_file_hash,
    is_supported,
    recognize_document,
    recognize_passport_batch,
)

logger = logging.getLogger("carcraft-backend")

_RECOGNITION_TASKS: set[asyncio.Task[None]] = set()
_MAX_ATTEMPTS = 3
_RETRY_BACKOFF_SECONDS = 2


SessionFactory = Callable[[], AsyncSession]


def schedule_recognition(
    *,
    document_id: UUID,
    user_id: UUID,
    document_type: str,
    file_bytes: bytes,
    filename: str,
    content_type: str,
    auto_approve: bool,
    session_factory: SessionFactory,
) -> None:
    """Spawn a background asyncio task for the recognition pipeline.

    The task reference is kept in a module-level set so the event loop
    does not garbage-collect it before completion.
    """
    if not is_supported(document_type):
        return
    task = asyncio.create_task(
        _run_recognition(
            document_id=document_id,
            user_id=user_id,
            document_type=document_type,
            file_bytes=file_bytes,
            filename=filename,
            content_type=content_type,
            auto_approve=auto_approve,
            session_factory=session_factory,
        )
    )
    _RECOGNITION_TASKS.add(task)
    task.add_done_callback(_RECOGNITION_TASKS.discard)


async def _run_recognition(
    *,
    document_id: UUID,
    user_id: UUID,
    document_type: str,
    file_bytes: bytes,
    filename: str,
    content_type: str,
    auto_approve: bool,
    session_factory: SessionFactory,
) -> None:
    file_hash = calculate_file_hash(file_bytes)
    try:
        async with session_factory() as session:
            cached = await cache_repo.get_cached(
                session,
                user_id=user_id,
                file_hash=file_hash,
                passport_type=document_type,
            )
            if cached is not None:
                await _persist_recognition(
                    session=session,
                    document_id=document_id,
                    auto_approve=auto_approve,
                    extracted_data=cached.get("raw_data"),
                    recognition_task_id=cached.get("recognition_task_id"),
                    error=None,
                )
                await session.commit()
                return
    except Exception as exc:
        logger.error(
            "document_recognition_cache_lookup_failed document_id=%s err=%s",
            document_id,
            exc,
        )

    result = await _recognize_with_retries(
        document_type=document_type,
        file_bytes=file_bytes,
        filename=filename,
        content_type=content_type,
    )
    logger.info(
        "document_recognition_finished document_id=%s success=%s task_id=%s error=%s",
        document_id,
        result.success,
        result.task_id,
        result.error,
    )

    try:
        async with session_factory() as session:
            if result.success and result.data is not None:
                try:
                    await cache_repo.save(
                        session,
                        user_id=user_id,
                        file_hash=file_hash,
                        passport_type=document_type,
                        raw_data=result.data,
                        mapped_data={"raw": result.data},
                        confidence_data={},
                        recognition_task_id=result.task_id,
                        document_id=document_id,
                    )
                except Exception as exc:
                    logger.warning(
                        "document_recognition_cache_save_failed "
                        "document_id=%s err=%s",
                        document_id,
                        exc,
                    )
            await _persist_recognition(
                session=session,
                document_id=document_id,
                auto_approve=auto_approve and result.success,
                extracted_data=result.data,
                recognition_task_id=result.task_id,
                error=result.error if not result.success else None,
            )
            await session.commit()
    except Exception as exc:
        logger.error(
            "document_recognition_persist_failed document_id=%s err=%s",
            document_id,
            exc,
        )


async def _persist_recognition(
    *,
    session: AsyncSession,
    document_id: UUID,
    auto_approve: bool,
    extracted_data: dict[str, Any] | None,
    recognition_task_id: str | None,
    error: str | None,
) -> None:
    new_review_status = STATUS_APPROVED if auto_approve else None
    await docs_repo.update_recognition(
        session,
        document_id,
        recognition_status="completed" if error is None else "error",
        extracted_data=extracted_data,
        recognition_task_id=recognition_task_id,
        recognition_error=error,
        review_status=new_review_status,
    )
    if new_review_status is not None:
        await hist_repo.append_document_status_history(
            document_id=document_id,
            old_status="pending",
            new_status=new_review_status,
            changed_by=None,
            comments="auto-approved by recognition",
        )


async def _recognize_with_retries(
    *,
    document_type: str,
    file_bytes: bytes,
    filename: str,
    content_type: str,
) -> RecognitionResult:
    last_error: str | None = None
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            result = await recognize_document(
                file_bytes,
                document_type,
                filename=filename,
                content_type=content_type,
            )
        except DocumentRecognitionError as exc:
            # Misconfiguration — retrying does not help.
            logger.warning(
                "document_recognition_unsupported document_type=%s err=%s",
                document_type,
                exc,
            )
            return RecognitionResult(success=False, error=str(exc))
        except Exception as exc:
            last_error = str(exc)
            logger.warning(
                "document_recognition_attempt_failed attempt=%s err=%s",
                attempt,
                exc,
            )
            if attempt < _MAX_ATTEMPTS:
                await asyncio.sleep(_RETRY_BACKOFF_SECONDS * attempt)
            continue
        if result.success:
            return result
        last_error = result.error
        if attempt < _MAX_ATTEMPTS:
            await asyncio.sleep(_RETRY_BACKOFF_SECONDS * attempt)
    return RecognitionResult(success=False, error=last_error)


def schedule_passport_recognition_for_user(
    *,
    user_id: UUID,
    pages: list[PassportPage],
    session_factory: SessionFactory,
) -> None:
    """Background batch recognition call keyed to ``user_id``.

    Used on the invite flow where the applicant uploads the signer's two
    passport pages *before* the signer has logged in. We don't create a
    ``documents`` row (there is no owning company in this context) — we
    only populate ``passport_recognition_data`` so the signer's СОПД
    render can find the structured fields by ``(user_id, passport_type)``.
    """
    if not pages:
        return
    task = asyncio.create_task(
        _run_passport_batch(
            user_id=user_id,
            pages=pages,
            session_factory=session_factory,
        )
    )
    _RECOGNITION_TASKS.add(task)
    task.add_done_callback(_RECOGNITION_TASKS.discard)


async def _lookup_passport_cache(
    *,
    session_factory: SessionFactory,
    user_id: UUID,
    pages: list[PassportPage],
    hashes: dict[str, str],
) -> dict[str, dict[str, Any]]:
    cached: dict[str, dict[str, Any]] = {}
    try:
        async with session_factory() as session:
            for page in pages:
                hit = await cache_repo.get_cached(
                    session,
                    user_id=user_id,
                    file_hash=hashes[page.passport_type],
                    passport_type=page.passport_type,
                )
                if hit is not None:
                    cached[page.passport_type] = hit
    except Exception as exc:
        logger.error(
            "passport_batch_cache_lookup_failed user_id=%s err=%s",
            user_id,
            exc,
        )
    return cached


async def _call_batch_recogniser(
    *, user_id: UUID, pages: list[PassportPage]
) -> dict[str, RecognitionResult]:
    try:
        batch = await recognize_passport_batch(pages)
        return dict(batch.per_page)
    except DocumentRecognitionError as exc:
        logger.warning(
            "passport_batch_unsupported user_id=%s err=%s", user_id, exc
        )
        error = str(exc)
    except Exception as exc:
        logger.warning(
            "passport_batch_transport_error user_id=%s err=%s", user_id, exc
        )
        error = str(exc)
    return {
        page.passport_type: RecognitionResult(success=False, error=error)
        for page in pages
    }


async def _run_passport_batch(
    *,
    user_id: UUID,
    pages: list[PassportPage],
    session_factory: SessionFactory,
) -> None:
    # Short-circuit on cache hits (same user uploaded the same bytes before).
    hashes = {p.passport_type: calculate_file_hash(p.file_bytes) for p in pages}
    cached_results = await _lookup_passport_cache(
        session_factory=session_factory,
        user_id=user_id,
        pages=pages,
        hashes=hashes,
    )

    to_recognise = [p for p in pages if p.passport_type not in cached_results]
    batch_results = (
        await _call_batch_recogniser(user_id=user_id, pages=to_recognise)
        if to_recognise
        else {}
    )

    try:
        async with session_factory() as session:
            passport_records = dict(cached_results)
            for page in pages:
                if page.passport_type in cached_results:
                    continue
                result = batch_results.get(page.passport_type)
                if result is None or not result.success or result.data is None:
                    logger.warning(
                        "passport_batch_recognition_failed "
                        "user_id=%s passport_type=%s err=%s",
                        user_id,
                        page.passport_type,
                        (result.error if result else "no result"),
                    )
                    continue
                passport_records[page.passport_type] = {"raw_data": result.data}
                try:
                    await cache_repo.save(
                        session,
                        user_id=user_id,
                        file_hash=hashes[page.passport_type],
                        passport_type=page.passport_type,
                        raw_data=result.data,
                        mapped_data={"raw": result.data},
                        confidence_data={},
                        recognition_task_id=result.task_id,
                        document_id=None,
                    )
                except Exception as exc:
                    logger.warning(
                        "passport_batch_cache_save_failed "
                        "user_id=%s passport_type=%s err=%s",
                        user_id,
                        page.passport_type,
                        exc,
                    )
            await _fill_profile_from_passport_records(
                session=session,
                user_id=user_id,
                passport_records=passport_records,
            )
            await session.commit()
    except Exception as exc:
        logger.error(
            "passport_batch_persist_failed user_id=%s err=%s", user_id, exc
        )


async def _fill_profile_from_passport_records(
    *,
    session: AsyncSession,
    user_id: UUID,
    passport_records: dict[str, dict[str, Any]],
) -> None:
    payload = profile_autofill_from_passport_records(
        main=passport_records.get(PASSPORT_MAIN_TYPE),
        registration=passport_records.get(PASSPORT_REGISTRATION_TYPE),
    )
    profile_payload = {
        key: value
        for key, value in payload.items()
        if key in {"birth_date", "address"}
    }
    await client_repo.fill_missing_profile_fields(
        session,
        user_id=user_id,
        profile_data=profile_payload,
    )


async def await_pending_tasks_for_tests() -> None:
    """Wait for currently-scheduled tasks. Used by integration tests only."""
    if not _RECOGNITION_TASKS:
        return
    pending = list(_RECOGNITION_TASKS)
    await asyncio.gather(*pending, return_exceptions=True)


def _make_default_session_factory() -> SessionFactory:
    """Return a callable producing fresh AsyncSession instances."""
    from infrastructure.database import AsyncSessionLocal

    def factory() -> AsyncSession:
        return AsyncSessionLocal()

    return factory


def default_session_factory() -> SessionFactory:
    """Public factory wrapper — used by handlers in production."""
    return _make_default_session_factory()


__all__ = [
    "SessionFactory",
    "await_pending_tasks_for_tests",
    "default_session_factory",
    "schedule_passport_recognition_for_user",
    "schedule_recognition",
]
