"""Verify phone-change SMS code and switch the user's phone."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from domain.errors import (
    InvalidPhoneChangeError,
    PhoneAlreadyInUseError,
    UserNotFoundError,
)
from infrastructure.repositories import client_repository as repo

logger = logging.getLogger("carcraft-backend")


@dataclass(frozen=True)
class VerifyPhoneChangeCommand:
    user_id: UUID
    new_phone: str
    code: str


async def handle_verify_phone_change(
    cmd: VerifyPhoneChangeCommand, session: AsyncSession
) -> None:
    existing_id = await repo.find_user_id_by_phone(session, cmd.new_phone)
    if existing_id is not None and existing_id != cmd.user_id:
        raise PhoneAlreadyInUseError()

    if not await repo.verify_phone_change_code(session, cmd.new_phone, cmd.code):
        raise InvalidPhoneChangeError()

    updated = await repo.update_phone(session, cmd.user_id, cmd.new_phone)
    if not updated:
        raise UserNotFoundError()

    await repo.delete_phone_change_codes(session, cmd.new_phone)
    logger.info("Phone changed for user %s -> %s", cmd.user_id, cmd.new_phone)
