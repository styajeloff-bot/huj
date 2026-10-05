"""Shared request hashing and receipt orchestration for application creation."""
from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.repositories import idempotency_repository


def request_hash(payload: dict[str, Any]) -> str:
    """Hash the JSON-compatible wire payload supplied by presentation."""
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


async def begin_application_create(
    session: AsyncSession,
    *,
    endpoint: str,
    key: str,
    payload: dict[str, Any],
) -> dict[str, Any] | None:
    return await idempotency_repository.begin(
        session,
        endpoint=endpoint,
        key=key,
        request_hash=request_hash(payload),
    )


async def finish_application_create(
    session: AsyncSession,
    *,
    endpoint: str,
    key: str,
    result: dict[str, Any],
) -> None:
    await idempotency_repository.succeed(
        session,
        endpoint=endpoint,
        key=key,
        response_snapshot=result,
    )
