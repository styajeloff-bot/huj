"""Repository helpers for verification_codes."""
from __future__ import annotations

from datetime import datetime
from typing import TypedDict, cast
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.models.users import VerificationCode
from infrastructure.repository_timing import timed_repository


class VerificationCodeDict(TypedDict):
    id: UUID
    phone: str | None
    code: str
    expires_at: datetime
    used_at: datetime | None
    failed_attempts: int
    created_at: datetime | None


def _to_dict(record: VerificationCode) -> VerificationCodeDict:
    return VerificationCodeDict(
        id=record.id,
        phone=record.phone,
        code=record.code,
        expires_at=cast("datetime", record.expires_at),
        used_at=cast("datetime | None", record.used_at),
        failed_attempts=int(record.failed_attempts or 0),
        created_at=cast("datetime | None", record.created_at),
    )


@timed_repository
async def count_recent_for_phone(
    session: AsyncSession, *, phone: str, purpose: str, since: datetime
) -> int:
    count = await session.scalar(
        sa.select(sa.func.count(VerificationCode.id)).where(
            VerificationCode.phone == phone,
            VerificationCode.purpose == purpose,
            VerificationCode.created_at >= since,
        )
    )
    return int(count or 0)


@timed_repository
async def create_code(
    session: AsyncSession,
    *,
    phone: str,
    code: str,
    expires_at: datetime,
    purpose: str,
    entity_id: str,
) -> VerificationCodeDict:
    now = datetime.now(expires_at.tzinfo)
    record = VerificationCode(
        phone=phone,
        code=code,
        expires_at=expires_at,
        purpose=purpose,
        entity_id=entity_id,
        created_at=now,
    )
    session.add(record)
    await session.flush()
    await session.refresh(record)
    return _to_dict(record)


@timed_repository
async def invalidate_active_codes(
    session: AsyncSession,
    *,
    purpose: str,
    entity_id: str,
    expires_at: datetime,
) -> None:
    await session.execute(
        sa.update(VerificationCode)
        .where(
            VerificationCode.purpose == purpose,
            VerificationCode.entity_id == entity_id,
            VerificationCode.used_at.is_(None),
            VerificationCode.expires_at > expires_at,
        )
        .values(expires_at=expires_at)
    )


@timed_repository
async def get_latest_code(
    session: AsyncSession, *, purpose: str, entity_id: str
) -> VerificationCodeDict | None:
    result = await session.execute(
        sa.select(VerificationCode)
        .where(
            VerificationCode.purpose == purpose,
            VerificationCode.entity_id == entity_id,
        )
        .order_by(VerificationCode.created_at.desc(), VerificationCode.id.desc())
        .limit(1)
    )
    record = result.scalars().first()
    return _to_dict(record) if record else None


@timed_repository
async def increment_failed_attempts(
    session: AsyncSession, *, code_id: UUID
) -> VerificationCodeDict | None:
    result = await session.execute(
        sa.update(VerificationCode)
        .where(VerificationCode.id == code_id)
        .values(failed_attempts=VerificationCode.failed_attempts + 1)
        .returning(VerificationCode)
    )
    record = result.scalars().first()
    return _to_dict(record) if record else None


@timed_repository
async def mark_used(
    session: AsyncSession, *, code_id: UUID, used_at: datetime
) -> VerificationCodeDict | None:
    result = await session.execute(
        sa.update(VerificationCode)
        .where(VerificationCode.id == code_id)
        .values(used_at=used_at)
        .returning(VerificationCode)
    )
    record = result.scalars().first()
    return _to_dict(record) if record else None
