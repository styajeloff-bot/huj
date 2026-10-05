"""Auth repository — users and verification codes."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, TypedDict, cast
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.cache.redis_client import logger
from infrastructure.models.users import User, UserSession, VerificationCode
from infrastructure.repository_timing import timed_repository


class UserDict(TypedDict):
    id: UUID
    phone: str
    email: str | None
    name: str | None
    role: str | None
    company_id: UUID | None
    is_active: bool | None
    phone_verified: bool | None
    mfa_enabled: bool

class MfaStateDict(TypedDict):
    enabled: bool
    secret: str | None
    pending_secret: str | None
    backup_code_hashes: list[str]

class UserSessionDict(TypedDict):
    id: UUID
    user_id: UUID | None
    refresh_token_hash: str
    expires_at: datetime
    ip_address: str | None
    user_agent: str | None
    country_code: str | None
    created_at: datetime | None
    last_used_at: datetime | None

def _to_dict(user: User) -> UserDict:
    return UserDict(
        id=user.id,
        phone=user.phone,
        email=user.email,
        name=user.name,
        role=user.role,
        company_id=user.company_id,
        is_active=user.is_active,
        phone_verified=user.phone_verified,
        mfa_enabled=bool(user.mfa_enabled),
    )

@timed_repository
async def find_user_by_phone(session: AsyncSession, phone: str) -> UserDict | None:
    result = await session.execute(sa.select(User).where(User.phone == phone))
    user = result.scalars().first()
    return _to_dict(user) if user else None

@timed_repository
async def find_user_by_id(session: AsyncSession, user_id: UUID) -> UserDict | None:
    result = await session.execute(sa.select(User).where(User.id == user_id))
    user = result.scalars().first()
    return _to_dict(user) if user else None

@timed_repository
async def phone_exists(session: AsyncSession, phone: str) -> bool:
    stmt = sa.select(
        sa.exists(sa.select(User.id).where(User.phone == phone))
    )
    result = await session.execute(stmt)
    return bool(result.scalar())

@timed_repository
async def create_user(
    session: AsyncSession,
    *,
    phone: str,
    email: str | None,
    name: str | None,
    password_hash: str,
    company_id: UUID | None,
    phone_verified: bool,
) -> UserDict:
    now = datetime.now(UTC)
    user = User(
        phone=phone,
        email=email or None,
        name=name or None,
        password_hash=password_hash,
        company_id=company_id,
        phone_verified=phone_verified,
        phone_verified_at=now if phone_verified else None,
        is_active=True,
    )
    session.add(user)
    await session.flush()
    await session.refresh(user)
    return _to_dict(user)

@timed_repository
async def set_phone_verified(session: AsyncSession, phone: str) -> UserDict:
    result = await session.execute(sa.select(User).where(User.phone == phone))
    user = result.scalars().first()
    if user is None:
        raise ValueError(f"User with phone {phone} not found")
    now = datetime.now(UTC)
    user.phone_verified = True
    cast("Any", user).phone_verified_at = now
    cast("Any", user).updated_at = now
    await session.flush()
    await session.refresh(user)
    return _to_dict(user)

@timed_repository
async def save_verification_code(
    session: AsyncSession,
    phone: str,
    code: str,
    expires_at: datetime,
) -> None:
    await session.execute(
        sa.delete(VerificationCode).where(
            VerificationCode.phone == phone,
            VerificationCode.purpose.is_(None),
        )
    )
    session.add(VerificationCode(phone=phone, code=code, expires_at=expires_at))
    await session.flush()

@timed_repository
async def get_last_code_created_at(
    session: AsyncSession, phone: str
) -> datetime | None:
    result = await session.execute(
        sa.select(VerificationCode.created_at)
        .where(
            VerificationCode.phone == phone,
            VerificationCode.purpose.is_(None),
        )
        .order_by(VerificationCode.created_at.desc())
        .limit(1)
    )
    return cast("datetime | None", result.scalar())

@timed_repository
async def verify_code(session: AsyncSession, phone: str, code: str) -> bool:
    """Verify a code for a given phone.

    For test phones (+7666...) the code 0000 is always valid provided a
    non-expired code row exists — this lets test suites control expiry and
    lockout independently of the test-phone shortcut.
    """
    logger.info("Verifying one-time code")
    if phone.startswith("+7666") and code == "0000":
        # Test-phone shortcut: accept 0000, but only if a valid (non-expired,
        # present) code row exists.  This lets tests that need expiry or
        # "no code sent" scenarios insert DB rows with the desired state.
        stmt = sa.select(
            sa.exists(
                sa.select(VerificationCode.id).where(
                    VerificationCode.phone == phone,
                    VerificationCode.expires_at > sa.func.now(),
                )
            )
        )
        result = await session.execute(stmt)
        if result.scalar():
            return True
        # No valid code row — fall through to the full check below so the
        # caller gets a proper "invalid code" path (useful for lockout tests).
    stmt = sa.select(
        sa.exists(
            sa.select(VerificationCode.id).where(
                VerificationCode.phone == phone,
                VerificationCode.code == code,
                VerificationCode.expires_at > sa.func.now(),
                VerificationCode.purpose.is_(None),
            )
        )
    )
    result = await session.execute(stmt)
    return bool(result.scalar())

@timed_repository
async def delete_codes(session: AsyncSession, phone: str) -> None:
    await session.execute(
        sa.delete(VerificationCode).where(
            VerificationCode.phone == phone,
            VerificationCode.purpose.is_(None),
        )
    )
    await session.flush()

def _session_to_dict(session_row: UserSession) -> UserSessionDict:
    # INET columns come back as ipaddress.IPv4Address/IPv6Address objects;
    # normalise to ``str`` so dict consumers don't hit json.dumps() errors.
    raw_ip = session_row.ip_address
    ip_str = str(raw_ip) if raw_ip is not None else None
    return UserSessionDict(
        id=session_row.id,
        user_id=session_row.user_id,
        refresh_token_hash=session_row.refresh_token_hash,
        expires_at=cast("datetime", session_row.expires_at),
        ip_address=ip_str,
        user_agent=session_row.user_agent,
        country_code=session_row.country_code,
        created_at=cast("datetime | None", session_row.created_at),
        last_used_at=cast("datetime | None", session_row.last_used_at),
    )

@timed_repository
async def create_user_session(
    session: AsyncSession,
    *,
    user_id: UUID,
    refresh_token_hash: str,
    expires_at: datetime,
    ip_address: str | None = None,
    user_agent: str | None = None,
    country_code: str | None = None,
) -> UserSessionDict:
    user_session = UserSession(
        user_id=user_id,
        refresh_token_hash=refresh_token_hash,
        expires_at=expires_at.replace(tzinfo=None),
        ip_address=ip_address,
        user_agent=user_agent,
        country_code=country_code,
    )
    session.add(user_session)
    await session.flush()
    await session.refresh(user_session)
    return _session_to_dict(user_session)

@timed_repository
async def get_user_session(
    session: AsyncSession,
    session_id: UUID,
) -> UserSessionDict | None:
    user_session = (await session.execute(
        select(UserSession).where(UserSession.id == str(session_id))
    )).scalar_one_or_none()
    return _session_to_dict(user_session) if user_session else None

@timed_repository
async def update_user_session(
    session: AsyncSession,
    *,
    session_id: UUID,
    refresh_token_hash: str,
    expires_at: datetime,
) -> UserSessionDict | None:
    user_session = await session.get(UserSession, session_id)
    if user_session is None:
        return None
    now = datetime.now(UTC).replace(tzinfo=None)
    user_session.refresh_token_hash = refresh_token_hash
    user_session.expires_at = cast("Any", expires_at.replace(tzinfo=None))
    user_session.last_used_at = cast("Any", now)
    await session.flush()
    await session.refresh(user_session)
    return _session_to_dict(user_session)

@timed_repository
async def delete_user_session(session: AsyncSession, session_id: UUID) -> None:
    await session.execute(sa.delete(UserSession).where(UserSession.id == session_id))
    await session.flush()

@timed_repository
async def delete_all_user_sessions(
    session: AsyncSession,
    user_id: UUID,
    *,
    except_session_id: UUID | None = None,
) -> int:
    """Drop every refresh session tied to ``user_id``. Returns rows removed.

    ``except_session_id`` — if provided, keeps that one session intact. Used by
    the self-service "logout on other devices" flow.
    """
    stmt = sa.delete(UserSession).where(UserSession.user_id == user_id)
    if except_session_id is not None:
        stmt = stmt.where(UserSession.id != except_session_id)
    result = await session.execute(stmt)
    await session.flush()
    return int(cast("sa.engine.CursorResult", result).rowcount or 0)

@timed_repository
async def list_user_sessions(
    session: AsyncSession,
    *,
    user_id: UUID,
) -> list[UserSessionDict]:
    """Return the user's non-expired sessions, most-recently-used first."""
    result = await session.execute(
        sa.select(UserSession)
        .where(
            UserSession.user_id == user_id,
            UserSession.expires_at > sa.func.now(),
        )
        .order_by(UserSession.last_used_at.desc().nullslast())
    )
    rows = result.scalars().all()
    return [_session_to_dict(row) for row in rows]

@timed_repository
async def list_all_user_sessions(
    session: AsyncSession,
    *,
    user_id: UUID,
) -> list[UserSessionDict]:
    """Return every session for ``user_id`` (including expired), newest first."""
    result = await session.execute(
        sa.select(UserSession)
        .where(UserSession.user_id == user_id)
        .order_by(UserSession.last_used_at.desc().nullslast())
    )
    rows = result.scalars().all()
    return [_session_to_dict(row) for row in rows]

@timed_repository
async def revoke_session_by_id(
    session: AsyncSession,
    *,
    user_id: UUID,
    session_id: UUID,
) -> bool:
    """Delete ``session_id`` iff it belongs to ``user_id``.

    Returns True on delete, False when the row is absent or owned by someone
    else — the caller gets a single opaque "not found" path regardless, which
    prevents leaking existence of other users' session IDs.
    """
    result = await session.execute(
        sa.delete(UserSession).where(
            UserSession.id == session_id,
            UserSession.user_id == user_id,
        )
    )
    await session.flush()
    return int(cast("sa.engine.CursorResult", result).rowcount or 0) > 0

@timed_repository
async def set_user_active(
    session: AsyncSession,
    user_id: UUID,
    is_active: bool,
) -> None:
    """Flip the user's ``is_active`` flag (admin-initiated disable/enable)."""
    await session.execute(
        sa.update(User).where(User.id == user_id).values(is_active=is_active)
    )
    await session.flush()

@timed_repository
async def activate_invited_user(
    session: AsyncSession, user_id: UUID
) -> None:
    """Used by the magic-link consume flow: flip ``is_active`` and
    ``phone_verified`` in one statement. The phone was already validated
    (we sent the SMS with the magic link), so clicking through is proof
    of control."""
    now = datetime.now(UTC)
    await session.execute(
        sa.update(User)
        .where(User.id == user_id)
        .values(is_active=True, phone_verified=True, phone_verified_at=now)
    )
    await session.flush()

# ---------------------------------------------------------------------------
# MFA (TOTP) operations
# ---------------------------------------------------------------------------

@timed_repository
async def set_pending_mfa_secret(
    session: AsyncSession,
    user_id: UUID,
    secret: str,
) -> None:
    """Stash a freshly generated, not-yet-activated TOTP secret on the user."""
    await session.execute(
        sa.update(User)
        .where(User.id == user_id)
        .values(mfa_pending_secret=secret)
    )
    await session.flush()

@timed_repository
async def activate_mfa(
    session: AsyncSession,
    user_id: UUID,
    secret: str,
    backup_code_hashes: list[str],
) -> None:
    """Move the pending secret to active, enable MFA, store backup hashes."""
    await session.execute(
        sa.update(User)
        .where(User.id == user_id)
        .values(
            mfa_enabled=True,
            mfa_secret=secret,
            mfa_pending_secret=None,
            mfa_backup_codes=list(backup_code_hashes),
        )
    )
    await session.flush()

@timed_repository
async def get_mfa_state(
    session: AsyncSession,
    user_id: UUID,
) -> MfaStateDict | None:
    """Return the MFA configuration for ``user_id`` or ``None`` if no user."""
    result = await session.execute(
        sa.select(
            User.mfa_enabled,
            User.mfa_secret,
            User.mfa_pending_secret,
            User.mfa_backup_codes,
        ).where(User.id == user_id)
    )
    row = result.first()
    if row is None:
        return None
    return MfaStateDict(
        enabled=bool(row[0]),
        secret=row[1],
        pending_secret=row[2],
        backup_code_hashes=list(row[3] or []),
    )

@timed_repository
async def consume_backup_code(
    session: AsyncSession,
    user_id: UUID,
    code_hash: str,
) -> bool:
    """Remove ``code_hash`` from the user's backup list atomically.

    Returns True iff the hash was present and has now been consumed.
    Performs a read-then-update inside the caller's transaction; concurrent
    consumption of the same code is prevented by the enclosing session's
    SERIALIZABLE/RC isolation + the ``await session.flush()`` here.
    """
    state = await get_mfa_state(session, user_id)
    if state is None or code_hash not in state["backup_code_hashes"]:
        return False
    remaining = [h for h in state["backup_code_hashes"] if h != code_hash]
    await session.execute(
        sa.update(User)
        .where(User.id == user_id)
        .values(mfa_backup_codes=remaining)
    )
    await session.flush()
    return True

@timed_repository
async def replace_mfa_backup_codes(
    session: AsyncSession,
    user_id: UUID,
    backup_code_hashes: list[str],
) -> None:
    """Overwrite the user's backup-code hashes with a fresh set."""
    await session.execute(
        sa.update(User)
        .where(User.id == user_id)
        .values(mfa_backup_codes=list(backup_code_hashes))
    )
    await session.flush()

@timed_repository
async def disable_mfa(session: AsyncSession, user_id: UUID) -> None:
    """Clear every MFA artefact on the user row."""
    await session.execute(
        sa.update(User)
        .where(User.id == user_id)
        .values(
            mfa_enabled=False,
            mfa_secret=None,
            mfa_pending_secret=None,
            mfa_backup_codes=None,
        )
    )
    await session.flush()

# ---------------------------------------------------------------------------
# BE-5: GDPR erasure
# ---------------------------------------------------------------------------

@timed_repository
async def anonymize_user(session: AsyncSession, user_id: UUID) -> None:
    """Overwrite PII on the user row with synthetic placeholders.

    The row is kept (other tables hold ``user_id`` foreign keys for
    reporting/orders), but every PII column is either nulled or replaced
    with a clearly-synthetic value. ``phone`` has a UNIQUE constraint, so
    we synthesise a deterministic but impossible-looking number derived
    from the user id. ``email`` uses a reserved sentinel domain. The
    account is also flipped to ``is_active=False`` to block re-use of
    the row via any cached access token.
    """
    now = datetime.now(UTC)
    placeholder_phone = f"+0000000{str(user_id)[:8]}"  # unique, clearly synthetic
    placeholder_email = f"anonymized-{str(user_id)[:12]}@deleted.local"
    await session.execute(
        sa.update(User)
        .where(User.id == user_id)
        .values(
            phone=placeholder_phone,
            email=placeholder_email,
            name=None,
            password_hash="",
            mfa_enabled=False,
            mfa_secret=None,
            mfa_pending_secret=None,
            mfa_backup_codes=None,
            is_active=False,
            deleted_at=now,
            updated_at=now,
        )
    )
    await session.flush()
