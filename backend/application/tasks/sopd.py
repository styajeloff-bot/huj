"""Render one СОПД PDF variant and cache it in S3.

Enqueued by the preview / download endpoints when no cache row exists,
and once at API-startup for the empty-context (blank) variant. The task
itself is idempotent: two concurrent enqueues for the same context hash
both render and upload, but only the first INSERT lands — ``upsert``
uses ``ON CONFLICT DO NOTHING``.
"""
from __future__ import annotations

import logging
from typing import Any

from infrastructure.database import AsyncSessionLocal
from infrastructure.repositories import sopd_render_cache_repository as cache_repo
from infrastructure.services.object_storage import get_object_storage
from infrastructure.services.sopd_renderer import (
    build_s3_key,
    compute_context_hash,
    compute_template_hash,
    render_pdf,
)
from infrastructure.taskiq_broker import broker

logger = logging.getLogger("carcraft-backend")


@broker.task(task_name="sopd.render")
async def render_sopd_pdf(context: dict[str, Any]) -> None:
    """Render a filled СОПД PDF for the given context and cache it.

    Context keys match the Jinja placeholders in ``sopd.md``:
    ``full_name``, ``birth_date``, ``birth_place``,
    ``passport_series_number``, ``passport_issued_by``,
    ``passport_issued_at``, ``passport_code``, ``address``, ``inn``,
    ``phone``, ``email``. Missing keys render as empty strings — the
    empty-context render is the "blank" template served to anyone who
    asks before passport data is available.
    """
    template_hash = compute_template_hash()
    context_hash = compute_context_hash(context)

    async with AsyncSessionLocal() as session:
        existing = await cache_repo.get_s3_key(
            session,
            template_hash=template_hash,
            context_hash=context_hash,
        )
        if existing is not None:
            return

    s3_key = build_s3_key(
        template_hash=template_hash, context_hash=context_hash
    )
    pdf_bytes = await render_pdf(context)
    storage = get_object_storage()
    await storage.put(s3_key, pdf_bytes, "application/pdf")

    async with AsyncSessionLocal() as session:
        try:
            await cache_repo.upsert(
                session,
                template_hash=template_hash,
                context_hash=context_hash,
                s3_key=s3_key,
            )
            await session.commit()
        except Exception:
            await session.rollback()
            raise

    logger.info(
        "sopd.render rendered template_hash=%s context_hash=%s key=%s "
        "bytes=%d",
        template_hash[:8],
        context_hash[:8],
        s3_key,
        len(pdf_bytes),
    )
