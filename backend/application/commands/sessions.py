"""Session-management handlers (user-facing + admin).

User-facing:
    * list own active sessions
    * revoke one own session by id

Admin (SecOps / support):
    * list all sessions for a target user
    * force-logout a target user (wipe every session)
    * disable / enable a target user
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.errors import ServiceError
from infrastructure.messaging import auth_events
from infrastructure.repositories import auth_repository as repo
from infrastructure.settings import settings


async def handle_list_my_sessions(
    user_id: UUID,
    session: AsyncSession,
    *,
    role: str | None = None,
) -> list[dict[str, Any]]:
    """Return the caller's active (non-expired, non-idle) sessions, newest first.

    Filters out rows whose ``last_used_at`` is older than the role-specific
    inactivity cap (see BE-1). A stale row would be rejected by
    ``handle_refresh_token`` anyway, so surfacing it here would only confuse
    the "active devices" UI. Rows with a NULL ``last_used_at`` fall back to
    ``created_at``; if both are NULL the row is kept (defensive — seed data
    or legacy migration artefacts shouldn't silently vanish).
    """
    rows = await repo.list_user_sessions(session, user_id=user_id)
    cap_hours = (
        settings.max_inactive_session_hours_employee
        if role == "carcraft_employee"
        else settings.max_inactive_session_hours_default
    )
    cutoff = datetime.now(UTC) - timedelta(hours=cap_hours)
    fresh: list[dict[str, Any]] = []
    for row in rows:
        last_used_at = row["last_used_at"] or row["created_at"]
        if last_used_at is None:
            fresh.append(dict(row))
            continue
        if last_used_at.tzinfo is None:
            last_used_at = last_used_at.replace(tzinfo=UTC)
        if last_used_at >= cutoff:
            fresh.append(dict(row))
    return fresh


async def handle_revoke_my_session(
    user_id: UUID,
    session_id: UUID,
    session: AsyncSession,
) -> None:
    """Revoke one session owned by ``user_id``.

    Raises ``ServiceError(404)`` if the id is unknown or owned by someone
    else — we don't differentiate to avoid leaking IDs.
    """
    revoked = await repo.revoke_session_by_id(
        session, user_id=user_id, session_id=session_id
    )
    if not revoked:
        raise ServiceError("Сессия не найдена", 404)
    auth_events.emit(
        auth_events.SESSION_REVOKED,
        user_id=user_id,
        session_id=session_id,
    )


async def handle_admin_list_sessions(
    target_user_id: UUID,
    session: AsyncSession,
) -> list[dict[str, Any]]:
    """Return every session (including expired) for ``target_user_id``.

    Caller must already hold the ``auth:admin`` scope — ownership is not
    enforced here.
    """
    rows = await repo.list_all_user_sessions(session, user_id=target_user_id)
    return [dict(row) for row in rows]


async def handle_admin_force_logout(
    target_user_id: UUID,
    session: AsyncSession,
) -> int:
    """Wipe every refresh session the target user has."""
    count = await repo.delete_all_user_sessions(session, target_user_id)
    auth_events.emit(
        auth_events.ADMIN_FORCE_LOGOUT,
        target_user_id=target_user_id,
        sessions_killed=count,
    )
    return cast("int", count)


async def handle_admin_disable_user(
    target_user_id: UUID,
    session: AsyncSession,
) -> None:
    """Deactivate the user and force-logout in one transaction."""
    await repo.set_user_active(session, target_user_id, is_active=False)
    killed = await repo.delete_all_user_sessions(session, target_user_id)
    auth_events.emit(
        auth_events.ADMIN_USER_DISABLED,
        target_user_id=target_user_id,
        sessions_killed=killed,
    )


async def handle_admin_enable_user(
    target_user_id: UUID,
    session: AsyncSession,
) -> None:
    """Re-activate the user. Does NOT reissue sessions — user must log in."""
    await repo.set_user_active(session, target_user_id, is_active=True)
    auth_events.emit(
        auth_events.ADMIN_USER_ENABLED,
        target_user_id=target_user_id,
    )
