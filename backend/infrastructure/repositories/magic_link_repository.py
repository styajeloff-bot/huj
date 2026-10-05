"""One-shot magic links (activation / passwordless login).

A token is 22 chars of URL-safe base64 (128 bits entropy). The repo is the
single entry point: callers never construct the token themselves.

Expected usage:
    link = await create(session, user_id=42, ttl_seconds=14 * 86400)
    send_sms(user.phone, f"{public_url}/s/{link.token}")
    ...
    link = await get_valid_by_token(session, token)  # raises / returns None
    await consume(session, link_id)
"""
from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.models.users import MagicLink
from infrastructure.repository_timing import timed_repository

_TOKEN_BYTES = 16  # → 22-char base64url string

def _generate_token() -> str:
    return secrets.token_urlsafe(_TOKEN_BYTES)

def _to_dict(row: MagicLink) -> dict[str, Any]:
    return {
        "id": row.id,
        "token": row.token,
        "user_id": row.user_id,
        "purpose": row.purpose,
        "expires_at": row.expires_at,
        "used_at": row.used_at,
        "created_at": row.created_at,
    }

@timed_repository
async def create(
    session: AsyncSession,
    *,
    user_id: UUID,
    ttl_seconds: int,
    purpose: str = "activation",
) -> dict[str, Any]:
    """Create a new one-shot link for ``user_id``. Returns dict with token."""
    record = MagicLink(
        token=_generate_token(),
        user_id=user_id,
        purpose=purpose,
        expires_at=datetime.now(UTC) + timedelta(seconds=ttl_seconds),
    )
    session.add(record)
    await session.flush()
    await session.refresh(record)
    return _to_dict(record)

@timed_repository
async def get_valid_by_token(
    session: AsyncSession, token: str
) -> dict[str, Any] | None:
    """Return the link row iff it exists, is unused, and not expired.

    Does not consume — call :func:`consume` after acting on it.
    """
    result = await session.execute(
        sa.select(MagicLink).where(MagicLink.token == token)
    )
    record = result.scalars().first()
    if record is None:
        return None
    if record.used_at is not None:
        return None
    # SQLAlchemy's Mapped[DateTime] type-stubs disagree with the concrete
    # datetime returned at runtime — mypy flags attr access on expires_at.
    expires: datetime = cast("datetime", record.expires_at)
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=UTC)
    if expires < datetime.now(UTC):
        return None
    return _to_dict(record)

@timed_repository
async def consume(session: AsyncSession, link_id: UUID) -> None:
    """Delete the link after a successful activation.

    We don't need the audit trail here — ``users.phone_verified_at`` already
    records when activation happened, and the magic-link row itself carries
    no information worth keeping past one use. Dropping the row also lets
    a subsequent re-invite skip conflict-handling.
    """
    await session.execute(
        sa.delete(MagicLink).where(MagicLink.id == link_id)
    )
    await session.flush()

@timed_repository
async def delete_expired(session: AsyncSession) -> int:
    """Purge links whose ``expires_at`` has passed. Returns the row count."""
    result = await session.execute(
        sa.delete(MagicLink).where(MagicLink.expires_at < datetime.now(UTC))
    )
    await session.flush()
    return int(cast("sa.engine.CursorResult", result).rowcount or 0)

@timed_repository
async def delete_unused_for_user(session: AsyncSession, user_id: UUID) -> int:
    """Invalidate a user's outstanding links. Used when the applicant
    re-sends an invite — we don't want two live magic-links pointing to
    the same account. Returns the row count."""
    result = await session.execute(
        sa.delete(MagicLink).where(MagicLink.user_id == user_id)
    )
    await session.flush()
    return int(cast("sa.engine.CursorResult", result).rowcount or 0)
