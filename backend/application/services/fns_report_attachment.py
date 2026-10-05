"""Attach the FNS bookkeeping PDF to a group of leasing applications.

At submit time (or admin dispatch) we read the freshest ``year_files[0]``
entry from the ``accounting_reports`` cache for the company's INN, pull the
PDF via HTTP from parser-api and drop it into ``documents`` + a
``document_applications`` link per application. The blob lives in one S3
object no matter how many clones the fan-out produced.

Failure is non-fatal — if the parser has no cached report, the PDF is
unreachable, or storage is unavailable, we log a warning and move on. The
accounting cache refreshes on its own when the user re-opens step 2, so a
missed attachment is recoverable without blocking the submit flow.
"""

from __future__ import annotations

import logging
import uuid

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.repositories import accounting_repository as accounting_repo
from infrastructure.repositories import documents_repository as documents_repo
from infrastructure.services import document_storage
from infrastructure.settings import settings

logger = logging.getLogger("carcraft-backend")

_FNS_DOCUMENT_TYPE = "fns_report"
_MAX_PDF_BYTES = 25 * 1024 * 1024
_REQUEST_TIMEOUT_SECONDS = 30


async def attach_fns_report_to_applications(
    session: AsyncSession,
    *,
    inn: str | None,
    company_id: uuid.UUID,
    application_ids: list[uuid.UUID],
) -> uuid.UUID | None:
    """Download the latest FNS PDF and link it to every application id.

    Idempotent: if one of the target applications already carries an
    ``fns_report``, we reuse that ``documents.id`` and just backfill
    ``document_applications`` for the apps that are missing the link. Only
    when no target has one do we hit the parser API and render+store a new
    blob.

    Returns the ``documents.id`` that ended up linked (whether reused or
    freshly created), or ``None`` when the attachment was skipped (no INN,
    no cached report, no usable URL, download/storage failure).
    """
    if not application_ids:
        return None

    already = await documents_repo.list_application_ids_with_document_type(
        session,
        application_ids=application_ids,
        document_type=_FNS_DOCUMENT_TYPE,
    )
    missing_ids = [a for a in application_ids if a not in already]
    if not missing_ids:
        logger.info(
            "fns_report_skip reason=already_attached inn=%s applications=%s",
            inn,
            application_ids,
        )
        return None

    # Reuse an existing fns_report already attached to one of the apps.
    existing_id: (
        uuid.UUID | None
    ) = await documents_repo.find_document_id_by_type_for_applications(
        session,
        application_ids=list(already),
        document_type=_FNS_DOCUMENT_TYPE,
    )
    if existing_id is not None:
        for app_id in missing_ids:
            await documents_repo.link_to_application(
                session, document_id=existing_id, application_id=app_id
            )
        logger.info(
            "fns_report_relinked document_id=%s applications=%s",
            existing_id,
            missing_ids,
        )
        return existing_id

    pulled = await _pull_pdf(session, inn=inn, application_ids=application_ids)
    if pulled is None:
        return None
    data, content_type, year = pulled
    stored = await _store_pdf(
        inn=inn or "unknown",
        company_id=company_id,
        data=data,
        content_type=content_type,
        year=year,
    )
    if stored is None:
        return None

    document_id: uuid.UUID = await documents_repo.create_document(
        session,
        company_id=company_id,
        document_type=_FNS_DOCUMENT_TYPE,
        file_name=_file_name(inn or "unknown", year),
        s3_key=stored.key,
        file_size=len(data),
        file_path=stored.public_url,
        related_application_id=application_ids[0],
        review_status="approved",
    )
    for app_id in application_ids:
        await documents_repo.link_to_application(
            session, document_id=document_id, application_id=app_id
        )

    logger.info(
        "fns_report_attached inn=%s document_id=%s applications=%s size=%s",
        inn,
        document_id,
        application_ids,
        len(data),
    )
    return document_id


async def _pull_pdf(
    session: AsyncSession,
    *,
    inn: str | None,
    application_ids: list[uuid.UUID],
) -> tuple[bytes, str | None, int | None] | None:
    if not inn or not application_ids:
        return None

    record = await accounting_repo.get_by_inn(session, inn)
    if record is None or record.get("fetch_status") != "success":
        logger.info(
            "fns_report_skip reason=no_cached_report inn=%s applications=%s",
            inn,
            application_ids,
        )
        return None

    pdf_url = _pick_pdf_url(record.get("year_files"))
    if not pdf_url:
        logger.info(
            "fns_report_skip reason=no_pdf_url inn=%s applications=%s",
            inn,
            application_ids,
        )
        return None

    data = await _download_pdf_bytes(inn, pdf_url)
    if data is None:
        return None

    return data[0], data[1], _pick_year(record.get("year_files"))


async def _download_pdf_bytes(
    inn: str, pdf_url: str
) -> tuple[bytes, str | None] | None:
    try:
        data, content_type = await _download(pdf_url)
    except Exception as exc:
        logger.warning(
            "fns_report_skip reason=download_failed inn=%s url=%s exc=%s",
            inn,
            pdf_url,
            exc,
        )
        return None

    if not data:
        logger.warning("fns_report_skip reason=empty_body inn=%s url=%s", inn, pdf_url)
        return None
    if len(data) > _MAX_PDF_BYTES:
        logger.warning(
            "fns_report_skip reason=oversize inn=%s size=%s url=%s",
            inn,
            len(data),
            pdf_url,
        )
        return None

    return data, content_type


async def _store_pdf(
    *,
    inn: str,
    company_id: uuid.UUID,
    data: bytes,
    content_type: str | None,
    year: int | None,
) -> document_storage.StoredDocument | None:
    key = document_storage.build_company_key(
        company_id, f"{uuid.uuid4().hex[:8]}_{_file_name(inn, year)}"
    )
    try:
        return await document_storage.put_document(
            key, data, content_type or "application/pdf"
        )
    except Exception as exc:
        logger.warning(
            "fns_report_skip reason=storage_failed inn=%s key=%s exc=%s",
            inn,
            key,
            exc,
        )
        return None


def _pick_pdf_url(year_files: object) -> str | None:
    if not isinstance(year_files, list):
        return None
    for item in year_files:
        if not isinstance(item, dict):
            continue
        url = item.get("pdf_url")
        if isinstance(url, str) and url.strip():
            return url.strip()
    return None


def _pick_year(year_files: object) -> int | None:
    if not isinstance(year_files, list):
        return None
    for item in year_files:
        if not isinstance(item, dict):
            continue
        year = item.get("year")
        if isinstance(year, int):
            return year
    return None


def _file_name(inn: str, year: int | None) -> str:
    suffix = f"-{year}" if year else ""
    return f"fns-report-{inn}{suffix}.pdf"


async def _download(url: str) -> tuple[bytes, str | None]:
    timeout = max(
        getattr(settings, "parser_api_timeout_ms", 15000) / 1000,
        _REQUEST_TIMEOUT_SECONDS,
    )
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        response = await client.get(url)
        response.raise_for_status()
        return response.content, response.headers.get("content-type")
