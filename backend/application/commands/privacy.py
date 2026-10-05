"""Privacy / GDPR commands.

Self-service data erasure (GDPR art. 17, 152-ФЗ ст. 14).

We implement **soft anonymization**: the ``users`` row is kept so foreign
keys on purchases, lease applications, and audit events keep pointing at a
valid id; instead every PII column is nulled or replaced with a synthetic
placeholder. Sessions are dropped outright (no reason to keep a refresh
token for an erased account) and the account is flipped to
``is_active=False`` so any leftover JWT cannot be used to log back in.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.messaging import auth_events
from infrastructure.repositories import auth_repository as repo

logger = logging.getLogger("carcraft-backend")


@dataclass
class EraseMyAccountCommand:
    user_id: UUID


async def handle_erase_my_account(
    cmd: EraseMyAccountCommand,
    session: AsyncSession,
) -> None:
    """Anonymize the caller's account.

    Idempotent: a second call on an already-erased user is a no-op. We
    detect the already-erased state by the ``is_active=False`` flag
    (anonymization sets it, and there's no self-service re-activation
    path). A missing row is also treated as a successful no-op — the
    caller authenticated with a valid JWT, so if the row is gone it
    was either erased by another request or reaped; either way there
    is nothing left to anonymize.
    """
    user = await repo.find_user_by_id(session, cmd.user_id)
    if user is None or not user["is_active"]:
        # Idempotent: already erased (or never existed). Still drop any
        # lingering sessions — cheap and defensive.
        await repo.delete_all_user_sessions(session, cmd.user_id)
        return

    # 1. Drop every refresh session — nothing useful can come of keeping them.
    await repo.delete_all_user_sessions(session, cmd.user_id)

    # 2. Wipe MFA side-artefacts first. ``anonymize_user`` does the same,
    #    but calling disable_mfa explicitly keeps the intent obvious and
    #    lets us reuse the existing helper.
    await repo.disable_mfa(session, cmd.user_id)

    # 3. Replace PII on the user row with synthetic placeholders.
    await repo.anonymize_user(session, cmd.user_id)

    # 4. Emit the audit event (carries user_id, never PII).
    auth_events.emit(auth_events.ACCOUNT_ERASED, user_id=cmd.user_id)
    logger.info("Account erased for user_id=%s", cmd.user_id)
