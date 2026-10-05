"""Persistence helpers for SOPD operator snapshots."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.models.sopd_operator_snapshots import SopdOperatorSnapshot
from infrastructure.repository_timing import timed_repository

DEFAULT_SOURCE = "application_selected_leasing_companies"


def _to_dict(record: SopdOperatorSnapshot) -> dict[str, Any]:
    return {
        "id": record.id,
        "signature_request_id": record.signature_request_id,
        "user_id": record.user_id,
        "application_id": record.application_id,
        "leasing_companies": record.leasing_companies,
        "contractors": record.contractors,
        "source": record.source,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
    }


@timed_repository
async def upsert(
    session: AsyncSession,
    *,
    signature_request_id: uuid.UUID,
    user_id: uuid.UUID,
    application_id: uuid.UUID | None,
    leasing_companies: list[dict[str, Any]],
    contractors: list[dict[str, Any]],
    source: str = DEFAULT_SOURCE,
) -> dict[str, Any]:
    now = datetime.now(UTC)
    insert_stmt = pg_insert(SopdOperatorSnapshot).values(
        signature_request_id=signature_request_id,
        user_id=user_id,
        application_id=application_id,
        leasing_companies=leasing_companies,
        contractors=contractors,
        source=source,
    )
    upsert_stmt = insert_stmt.on_conflict_do_update(
        index_elements=["signature_request_id"],
        set_={
            "user_id": user_id,
            "application_id": application_id,
            "leasing_companies": leasing_companies,
            "contractors": contractors,
            "source": source,
            "updated_at": now,
        },
    ).returning(SopdOperatorSnapshot)
    result = await session.execute(upsert_stmt)
    record = result.scalars().one()
    await session.flush()
    return _to_dict(record)


@timed_repository
async def get_by_signature_request_id(
    session: AsyncSession, signature_request_id: uuid.UUID
) -> dict[str, Any] | None:
    result = await session.execute(
        sa.select(SopdOperatorSnapshot).where(
            SopdOperatorSnapshot.signature_request_id == signature_request_id
        )
    )
    record = result.scalars().first()
    return _to_dict(record) if record else None


@timed_repository
async def list_for_user(
    session: AsyncSession, user_id: uuid.UUID
) -> list[dict[str, Any]]:
    result = await session.execute(
        sa.select(SopdOperatorSnapshot)
        .where(SopdOperatorSnapshot.user_id == user_id)
        .order_by(SopdOperatorSnapshot.created_at.desc())
    )
    return [_to_dict(record) for record in result.scalars().all()]
