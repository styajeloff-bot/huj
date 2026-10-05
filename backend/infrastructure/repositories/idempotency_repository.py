"""Transactional application-create idempotency state."""
from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from typing import Any

import sqlalchemy as sa
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from domain.errors import ApplicationCreateIdempotencyConflictError
from infrastructure.models.idempotency import IdempotencyKey


def _advisory_lock_id(endpoint: str, key: str) -> int:
    raw = hashlib.blake2b(f"{endpoint}:{key}".encode(), digest_size=8).digest()
    return int.from_bytes(raw, byteorder="big", signed=True)


async def begin(
    session: AsyncSession,
    *,
    endpoint: str,
    key: str,
    request_hash: str,
    ttl: timedelta = timedelta(minutes=30),
) -> dict[str, Any] | None:
    """Acquire a create attempt, or return the canonical successful response."""
    bind = session.get_bind()
    if bind.dialect.name == "postgresql":
        locked = await session.scalar(
            select(sa.func.pg_try_advisory_xact_lock(_advisory_lock_id(endpoint, key)))
        )
        if not locked:
            raise ApplicationCreateIdempotencyConflictError(
                "Idempotency-Key уже обрабатывается; повторите запрос через короткий интервал",
            )

    now = datetime.now(UTC)
    row = await session.scalar(
        select(IdempotencyKey).where(
            IdempotencyKey.endpoint == endpoint,
            IdempotencyKey.idempotency_key == key,
        )
    )
    if row is not None and row.expires_at <= now:
        await session.delete(row)
        await session.flush()
        row = None
    if row is not None:
        if row.request_hash != request_hash:
            raise ApplicationCreateIdempotencyConflictError("Idempotency-Key уже используется с другим payload")
        if row.status == "succeeded" and row.response_snapshot is not None:
            return dict(row.response_snapshot)
        if row.status == "in_progress":
            raise ApplicationCreateIdempotencyConflictError(
                "Idempotency-Key уже обрабатывается; повторите запрос через короткий интервал",
            )
        await session.delete(row)
        await session.flush()

    session.add(IdempotencyKey(
        endpoint=endpoint,
        idempotency_key=key,
        status="in_progress",
        request_hash=request_hash,
        response_snapshot=None,
        created_at=now,
        expires_at=now + ttl,
    ))
    await session.flush()
    return None


async def succeed(
    session: AsyncSession,
    *,
    endpoint: str,
    key: str,
    response_snapshot: dict[str, Any],
) -> None:
    row = await session.scalar(
        select(IdempotencyKey).where(
            IdempotencyKey.endpoint == endpoint,
            IdempotencyKey.idempotency_key == key,
        )
    )
    if row is None:
        raise RuntimeError("Idempotency receipt disappeared before commit")
    row.status = "succeeded"
    row.response_snapshot = response_snapshot
    await session.flush()
