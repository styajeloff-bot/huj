"""Send calculation by email — command + handler."""
from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from application.errors import ServiceError
from infrastructure.services.email_sender import send_email

logger = logging.getLogger("carcraft-backend")


@dataclass
class SendCalculationEmailCommand:
    to: str
    subject: str
    text: str | None = None
    html: str | None = None


async def handle_send_calculation_email(
    cmd: SendCalculationEmailCommand,
    _session: AsyncSession,
) -> None:
    """Send a calculator-generated email.

    The session is unused — kept for handler signature consistency.
    """
    body = cmd.text or ""
    if not body and not cmd.html:
        raise ServiceError(
            "Не указан ни текст, ни HTML тела письма", status_code=400
        )
    try:
        await send_email(
            cmd.to,
            cmd.subject,
            body,
            html=cmd.html,
        )
    except Exception as exc:
        logger.exception("Failed to send calculator email")
        raise ServiceError(
            "Не удалось отправить письмо", status_code=502
        ) from exc
