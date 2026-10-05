"""Passport recognition cache repository.

Recognition-provider calls are slow and metered; this table caches parsed results per
``(user_id, file_hash, passport_type)`` so a duplicate upload of the same
image short-circuits to the cached structure.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.models.documents import PassportRecognitionData
from infrastructure.repository_timing import timed_repository


def _to_dict(row: PassportRecognitionData) -> dict[str, Any]:
    return {
        "id": row.id,
        "user_id": row.user_id,
        "document_id": row.document_id,
        "file_hash": row.file_hash,
        "passport_type": row.passport_type,
        "raw_data": row.raw_data,
        "mapped_data": row.mapped_data,
        "confidence_data": row.confidence_data,
        "recognition_task_id": row.dbrain_task_id,
    }


@timed_repository
async def get_by_id_for_user(
    session: AsyncSession,
    *,
    recognition_id: UUID,
    user_id: UUID,
    passport_type: str,
) -> dict[str, Any] | None:
    stmt = select(PassportRecognitionData).where(
        PassportRecognitionData.id == recognition_id,
        PassportRecognitionData.user_id == user_id,
        PassportRecognitionData.passport_type == passport_type,
    )
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        return None
    return _to_dict(row)


@timed_repository
async def get_cached(
    session: AsyncSession,
    *,
    user_id: UUID,
    file_hash: str,
    passport_type: str,
) -> dict[str, Any] | None:
    stmt = select(PassportRecognitionData).where(
        PassportRecognitionData.user_id == user_id,
        PassportRecognitionData.file_hash == file_hash,
        PassportRecognitionData.passport_type == passport_type,
    )
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        return None
    return _to_dict(row)


@timed_repository
async def save(
    session: AsyncSession,
    *,
    user_id: UUID,
    file_hash: str,
    passport_type: str,
    raw_data: dict[str, Any],
    mapped_data: dict[str, Any],
    confidence_data: dict[str, Any],
    recognition_task_id: str | None,
    document_id: UUID | None = None,
) -> UUID:
    row = PassportRecognitionData(
        user_id=user_id,
        file_hash=file_hash,
        passport_type=passport_type,
        raw_data=raw_data,
        mapped_data=mapped_data,
        confidence_data=confidence_data,
        dbrain_task_id=recognition_task_id,
        document_id=document_id,
    )
    session.add(row)
    await session.flush()
    return row.id


@timed_repository
async def link_document(
    session: AsyncSession,
    *,
    recognition_id: UUID,
    document_id: UUID,
) -> bool:
    row = await session.get(PassportRecognitionData, recognition_id)
    if row is None:
        return False
    row.document_id = document_id
    await session.flush()
    return True


@timed_repository
async def get_latest_for_user(
    session: AsyncSession,
    *,
    user_id: UUID,
    passport_type: str,
) -> dict[str, Any] | None:
    """Most recent recognition row for (user_id, passport_type), if any.

    Used by the СОПД render pipeline to resolve structured passport data
    for the current signer — a signer can re-upload, and we always
    trust the freshest successful recognition.
    """
    stmt = (
        select(PassportRecognitionData)
        .where(
            PassportRecognitionData.user_id == user_id,
            PassportRecognitionData.passport_type == passport_type,
        )
        .order_by(PassportRecognitionData.id.desc())
        .limit(1)
    )
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        return None
    return _to_dict(row)


__all__ = [
    "get_by_id_for_user",
    "get_cached",
    "get_latest_for_user",
    "link_document",
    "save",
]
