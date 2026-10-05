"""Request phone change — send SMS verification code to the new phone number."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from domain.errors import PhoneAlreadyInUseError
from infrastructure.repositories import client_repository as repo
from infrastructure.services.sms import (
    get_verification_code,
    is_test_phone,
    send_verification_sms,
)

logger = logging.getLogger("carcraft-backend")

_CODE_EXPIRY_MINUTES = 10
_sms_tasks: set[asyncio.Task[None]] = set()


@dataclass(frozen=True)
class RequestPhoneChangeCommand:
    user_id: UUID
    new_phone: str


async def _send_sms_background(phone: str, code: str) -> None:
    try:
        await send_verification_sms(phone, code, sms_type="phone_change")
    except Exception as exc:
        logger.error("Background phone-change SMS failed for %s: %s", phone, exc)


def _fire_sms(phone: str, code: str) -> None:
    if is_test_phone(phone):
        return
    task = asyncio.create_task(_send_sms_background(phone, code))
    _sms_tasks.add(task)
    task.add_done_callback(_sms_tasks.discard)


async def handle_request_phone_change(
    cmd: RequestPhoneChangeCommand, session: AsyncSession
) -> None:
    existing_id = await repo.find_user_id_by_phone(session, cmd.new_phone)
    if existing_id is not None and existing_id != cmd.user_id:
        raise PhoneAlreadyInUseError()

    code = get_verification_code(cmd.new_phone)
    expires_at = datetime.now(UTC) + timedelta(minutes=_CODE_EXPIRY_MINUTES)
    await repo.save_phone_change_code(session, cmd.new_phone, code, expires_at)
    _fire_sms(cmd.new_phone, code)
    logger.info("Phone change requested for user %s -> %s", cmd.user_id, cmd.new_phone)
