"""Lookup/upsert for the СОПД render cache (``sopd_rendered_pdfs``)."""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.models.sopd_cache import SopdRenderedPdf
from infrastructure.repository_timing import timed_repository


@timed_repository
async def get_s3_key(
    session: AsyncSession, *, template_hash: str, context_hash: str
) -> str | None:
    """Return the stored S3 key for a (template, context) pair, if any."""
    result = await session.execute(
        sa.select(SopdRenderedPdf.s3_key).where(
            SopdRenderedPdf.template_hash == template_hash,
            SopdRenderedPdf.context_hash == context_hash,
        )
    )
    return result.scalar_one_or_none()

@timed_repository
async def upsert(
    session: AsyncSession,
    *,
    template_hash: str,
    context_hash: str,
    s3_key: str,
) -> None:
    """Insert a cache row; on PK conflict keep the existing row.

    Concurrent renders for the same key hit the S3 upload twice but the
    second INSERT is a no-op — we deliberately accept the duplicated
    upload (rare race; costs one extra PUT) rather than hold a DB lock
    across a multi-second LibreOffice invocation.
    """
    stmt = pg_insert(SopdRenderedPdf).values(
        template_hash=template_hash,
        context_hash=context_hash,
        s3_key=s3_key,
    )
    stmt = stmt.on_conflict_do_nothing(
        index_elements=["template_hash", "context_hash"]
    )
    await session.execute(stmt)
    await session.flush()
