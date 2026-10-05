"""Admin-initiated MFA reset (account recovery).

If a user loses every 2FA factor (phone + authenticator + backup codes),
there is no self-serve path back. SecOps / support can invoke this
handler after offline identity verification; it wipes every MFA artefact
on the user row and kills every refresh session so the next login is
clean.

Lives in its own module (not ``sessions.py``) because the reset is
distinctly an account-recovery concern — keeping it separate from the
session-management handlers keeps both files readable.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.errors import ServiceError
from domain.errors import UserNotFoundError
from infrastructure.messaging import auth_events
from infrastructure.repositories import auth_repository as repo


@dataclass
class AdminResetMfaCommand:
    """Reset MFA for ``target_user_id`` on behalf of ``by_user_id``.

    ``reason`` is a free-form audit-trail string (e.g. a support ticket
    ID); it is emitted verbatim on the audit event and is required so
    the action is always traceable to an offline verification step.
    """

    target_user_id: UUID
    reason: str
    by_user_id: UUID


async def handle_admin_reset_mfa(
    cmd: AdminResetMfaCommand,
    session: AsyncSession,
) -> int:
    """Disable MFA for the target user and wipe every session.

    Returns the number of sessions that were killed so the router can
    surface it to the admin client (useful to confirm the blast radius).
    Raises :class:`UserNotFoundError` (404) when the target is unknown
    and :class:`ServiceError` (400) when MFA is not currently enabled —
    refuse the no-op so audit trails can't be padded with meaningless
    resets.
    """
    user = await repo.find_user_by_id(session, cmd.target_user_id)
    if user is None:
        raise UserNotFoundError()
    state = await repo.get_mfa_state(session, cmd.target_user_id)
    if state is None or not state["enabled"]:
        raise ServiceError("MFA у этого пользователя не включена", 400)

    await repo.disable_mfa(session, cmd.target_user_id)
    killed = await repo.delete_all_user_sessions(session, cmd.target_user_id)

    auth_events.emit(
        auth_events.ADMIN_MFA_RESET,
        target_user_id=cmd.target_user_id,
        by_user_id=cmd.by_user_id,
        reason=cmd.reason,
        sessions_killed=killed,
    )
    return cast("int", killed)
