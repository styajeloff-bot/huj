"""Email preferences commands."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from application.errors import ServiceError
from application.notifications.templates import next_delivery_at
from infrastructure.repositories.auth_repository import find_user_by_id
from infrastructure.repositories.email_preferences_repository import (
    EmailPreferencesDict,
    get_or_default,
    update_preferences,
)
from infrastructure.repositories.notification_email_repository import (
    reschedule_user_pending,
)
from infrastructure.services.email_sender import send_email
from infrastructure.settings import settings

logger = logging.getLogger("carcraft-backend")


@dataclass
class UpdateEmailPreferencesCommand:
    user_id: UUID
    updates: dict[str, Any]


async def handle_update_email_preferences(
    command: UpdateEmailPreferencesCommand, session: AsyncSession
) -> EmailPreferencesDict:
    if not command.updates:
        raise ServiceError("Нет данных для обновления", status_code=400)
    previous = await get_or_default(session, command.user_id)
    result = await update_preferences(session, command.user_id, command.updates)
    if result is None:
        raise ServiceError("Email preferences not found", status_code=404)
    if result["email_frequency"] != previous["email_frequency"]:
        mode = result["email_frequency"]
        await reschedule_user_pending(
            session,
            command.user_id,
            mode,
            next_delivery_at(
                datetime.now(UTC),
                mode,
                timezone=settings.notification_business_timezone,
                hour=settings.notification_digest_hour,
                weekday=settings.notification_digest_weekday,
            ),
        )
    return cast("EmailPreferencesDict", result)


# ---------------------------------------------------------------------------
# Admin: send test email
# ---------------------------------------------------------------------------


@dataclass
class SendTestEmailCommand:
    """Send a test SMTP email.

    The handler resolves the recipient as ``override_to`` when present,
    otherwise the current user's email loaded from the DB. When neither
    is available the handler raises a 400 ``ServiceError``.
    """

    user_id: UUID
    override_to: str | None = None


@dataclass
class SendTestEmailResult:
    sent_to: str


async def handle_send_test_email(
    command: SendTestEmailCommand,
    session: AsyncSession,
) -> SendTestEmailResult:
    if command.override_to:
        target = command.override_to.strip()
    else:
        user = await find_user_by_id(session, command.user_id)
        target = (user["email"] or "").strip() if user else ""

    if not target:
        raise ServiceError(
            "У пользователя не указан email и адрес-получатель не передан",
            status_code=400,
        )

    timestamp = datetime.now(UTC).isoformat(timespec="seconds")
    subject = "CarCraft: тестовое письмо"
    body = (
        "Это тестовое письмо от системы CarCraft.\n\n"
        f"Время отправки (UTC): {timestamp}\n"
        f"Получатель: {target}\n\n"
        "Если вы получили это сообщение, SMTP-конфигурация работает корректно."
    )
    try:
        await send_email(target, subject, body)
    except Exception as exc:
        logger.exception("Failed to send test email to %s", target)
        raise ServiceError(
            "Не удалось отправить тестовое письмо",
            status_code=502,
        ) from exc
    return SendTestEmailResult(sent_to=target)
