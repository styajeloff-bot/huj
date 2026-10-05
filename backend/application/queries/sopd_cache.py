"""Shared cache-lookup + enqueue helper for the СОПД render pipeline.

Two endpoints need the exact same dance:

    1. Compute ``(template_hash, context_hash)``.
    2. If a row exists, fetch the PDF from S3.
    3. Otherwise enqueue ``sopd.render`` and tell the caller to retry.

Both endpoints call :func:`resolve_sopd_pdf` and get back a discriminated
result object. Routers translate the result into the appropriate HTTP
response (200 / 202 / 404).
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from application.tasks.sopd import render_sopd_pdf
from domain.services.object_storage import ObjectStorage
from infrastructure.repositories import sopd_render_cache_repository as cache_repo
from infrastructure.services.sopd_renderer import (
    SopdTemplateUnavailableError,
    compute_context_hash,
    compute_template_hash,
)

logger = logging.getLogger("carcraft-backend")


@dataclass(frozen=True)
class SopdPdfReady:
    data: bytes
    media_type: str = "application/pdf"


@dataclass(frozen=True)
class SopdPdfPending:
    """The PDF is not yet cached; a render task has been enqueued."""


@dataclass(frozen=True)
class SopdTemplateMissing:
    """The .docx template isn't present in the image at all — operator bug."""

    detail: str


SopdPdfResult = SopdPdfReady | SopdPdfPending | SopdTemplateMissing


async def resolve_sopd_pdf(
    *,
    session: AsyncSession,
    storage: ObjectStorage,
    context: dict[str, Any],
) -> SopdPdfResult:
    """Hit the cache; on miss enqueue the render task and signal pending."""
    try:
        template_hash = compute_template_hash()
    except SopdTemplateUnavailableError as exc:
        return SopdTemplateMissing(detail=str(exc))
    context_hash = compute_context_hash(context)

    s3_key = await cache_repo.get_s3_key(
        session,
        template_hash=template_hash,
        context_hash=context_hash,
    )
    if s3_key is not None:
        stored = await storage.get(s3_key)
        if stored is not None:
            return SopdPdfReady(data=stored.data)
        # Cache row points at a missing object — re-render.
        logger.warning(
            "sopd_cache orphan row template_hash=%s context_hash=%s key=%s",
            template_hash[:8],
            context_hash[:8],
            s3_key,
        )

    await render_sopd_pdf.kiq(context)
    return SopdPdfPending()


async def wait_for_sopd_pdf(
    *,
    session: AsyncSession,
    storage: ObjectStorage,
    context: dict[str, Any],
    timeout_seconds: float,
    poll_interval_seconds: float = 0.25,
) -> bytes | None:
    """Poll the render cache for up to ``timeout_seconds`` after an enqueue.

    Used by the download endpoint so the UX never sees a 202 for short
    renders — callers can wait a few seconds inline and only fall through
    to the static fallback if the worker is genuinely slow. Returns the
    PDF bytes on success, or ``None`` if the deadline expires.
    """
    try:
        template_hash = compute_template_hash()
    except SopdTemplateUnavailableError:
        return None
    context_hash = compute_context_hash(context)

    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_seconds
    while True:
        s3_key = await cache_repo.get_s3_key(
            session,
            template_hash=template_hash,
            context_hash=context_hash,
        )
        if s3_key is not None:
            stored = await storage.get(s3_key)
            if stored is not None:
                return stored.data
        if loop.time() >= deadline:
            return None
        await asyncio.sleep(poll_interval_seconds)


async def ensure_sopd_pdf(
    *,
    session: AsyncSession,
    storage: ObjectStorage,
    context: dict[str, Any],
) -> bytes:
    """Return the filled СОПД PDF bytes, rendering inline on cache miss.

    Used on the signing path where we cannot tell the caller to retry —
    once the user clicks «Подписать» we must produce the exact PDF that
    will be stored as the signed artefact. The common case is a cache
    hit (the preview already primed it); the miss path pays the full
    WeasyPrint cost on the request thread.
    """
    from infrastructure.services.sopd_renderer import (
        build_s3_key,
        render_pdf,
    )

    template_hash = compute_template_hash()
    context_hash = compute_context_hash(context)

    s3_key = await cache_repo.get_s3_key(
        session,
        template_hash=template_hash,
        context_hash=context_hash,
    )
    if s3_key is not None:
        stored = await storage.get(s3_key)
        if stored is not None:
            return stored.data

    pdf_bytes = await render_pdf(context)
    new_key = build_s3_key(
        template_hash=template_hash, context_hash=context_hash
    )
    await storage.put(new_key, pdf_bytes, "application/pdf")
    await cache_repo.upsert(
        session,
        template_hash=template_hash,
        context_hash=context_hash,
        s3_key=new_key,
    )
    return pdf_bytes
