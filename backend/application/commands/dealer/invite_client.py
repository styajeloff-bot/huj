"""Dealer invite-client command.

Sends an SMS verification code to a phone number so the prospective client
can register. If the phone is new, we create a minimal ``users`` row with
role=``client`` (phone is the unique identifier in this codebase); if the
phone is already taken, we silently re-send the code — mirrors the Express
behaviour of treating re-invitation as idempotent.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from domain.errors import DealerInviteError
from infrastructure.repositories import auth_repository as repo
from infrastructure.services import sms as sms_service

logger = logging.getLogger("carcraft-backend")

# Invite code lives slightly longer than the login OTP (15 min) so the
# recipient has time to open the link, install the app, etc.
_CODE_TTL_MINUTES = 15

_PHONE_RE = re.compile(r"^\+7\d{10}$")


@dataclass
class InviteClientCommand:
    actor_id: UUID
    actor_role: str
    phone: str
    name: str | None = None
    email: str | None = None


async def handle_invite_client(
    cmd: InviteClientCommand, session: AsyncSession
) -> dict[str, Any]:
    phone = _normalise_phone(cmd.phone)
    if cmd.actor_role not in {"dealer", "carcraft_employee"}:
        # Scope guard in the router catches this first — belt-and-braces.
        raise DealerInviteError("Только дилеры и сотрудники могут отправлять инвайт")

    existing = await repo.find_user_by_phone(session, phone)
    created = False
    if existing is None:
        # Fresh user — minimal client account, phone_verified=False; the
        # code they receive is the registration code.
        await repo.create_user(
            session,
            phone=phone,
            email=cmd.email or None,
            name=cmd.name or None,
            password_hash="",
            company_id=None,
            phone_verified=False,
        )
        created = True

    code = sms_service.get_verification_code(phone)
    expires_at = datetime.now(UTC) + timedelta(minutes=_CODE_TTL_MINUTES)
    await repo.save_verification_code(session, phone, code, expires_at)

    # SMS send is best-effort: logging on failure, we still persist the
    # verification code so the client can be given it out-of-band.
    try:
        await sms_service.send_verification_sms(
            phone, code, sms_type="registration"
        )
    except Exception as exc:
        logger.warning(
            "Dealer invite: SMS send failed for phone=%s: %s", phone, exc
        )

    logger.info(
        "Dealer %s invited client phone=%s (new=%s)",
        cmd.actor_id,
        phone,
        created,
    )
    return {
        "success": True,
        "message": "Приглашение отправлено клиенту",
        "created_user": created,
    }


def _normalise_phone(raw: str) -> str:
    trimmed = (raw or "").strip().replace(" ", "").replace("-", "")
    if trimmed.startswith("8") and len(trimmed) == 11:
        trimmed = "+7" + trimmed[1:]
    elif trimmed.startswith("7") and len(trimmed) == 11:
        trimmed = "+" + trimmed
    if not _PHONE_RE.match(trimmed):
        raise DealerInviteError("Некорректный номер телефона (ожидается +7XXXXXXXXXX)")
    return trimmed
