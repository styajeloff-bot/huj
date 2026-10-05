"""Transactional security notifications — email + SMS dispatch helpers.

Each function composes a subject/body (Russian text) for one class of
security-sensitive auth event and dispatches to whichever channels the
user has configured:

- Email via SMTP if ``user['email']`` is set.
- SMS via the SMSC gateway (:func:`infrastructure.services.sms.send_text_sms`)
  if ``user['phone']`` is set.

Partial failure policy: a broken SMTP connection must not suppress the
SMS, and vice versa. Failures are logged at ``WARNING`` and swallowed —
missing a security alert is preferable to stalling the Kafka consumer
on a flaky downstream.

Email backend: a thin wrapper around :mod:`smtplib` run in a worker
thread. The rest of the service already uses this pattern (see
``sms.py``) so we avoid pulling in ``aiosmtplib`` as a new dependency.
"""
from __future__ import annotations

import asyncio
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

from infrastructure.services.sms import send_text_sms
from infrastructure.settings import settings

logger = logging.getLogger("carcraft-backend")


# ---------------------------------------------------------------------------
# Email backend
# ---------------------------------------------------------------------------


def _send_email_blocking(to: str, subject: str, body: str) -> None:
    """Synchronous SMTP send — called via ``asyncio.to_thread``.

    Uses the same SMTP credentials the SMS gateway relies on
    (`settings.smtp_*`). Port 465 → SMTP_SSL; any other port → STARTTLS.
    """
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = settings.smtp_user
    msg["To"] = to
    msg.attach(MIMEText(body, "plain", "utf-8"))

    host, port = settings.smtp_host, settings.smtp_port
    if port == 465:
        with smtplib.SMTP_SSL(host, port) as smtp:
            smtp.login(settings.smtp_user, settings.smtp_password)
            smtp.send_message(msg)
    else:
        with smtplib.SMTP(host, port) as smtp:
            smtp.starttls()
            smtp.login(settings.smtp_user, settings.smtp_password)
            smtp.send_message(msg)


async def send_email(to: str, subject: str, body: str) -> None:
    """Send a plain-text email. Raises on failure — callers decide how to react."""
    await asyncio.to_thread(_send_email_blocking, to, subject, body)
    logger.info("security_email_sent to=%s subject=%s", to, subject)


# ---------------------------------------------------------------------------
# Dispatch helper
# ---------------------------------------------------------------------------


async def _dispatch(
    user: dict[str, Any],
    *,
    event_name: str,
    subject: str,
    email_body: str,
    sms_text: str,
) -> None:
    """Send email + SMS tolerating partial failure on either channel."""
    email = user.get("email")
    phone = user.get("phone")

    if email:
        try:
            await send_email(email, subject, email_body)
        except Exception as exc:
            logger.warning(
                "security_email_failed event=%s user_id=%s err=%s",
                event_name,
                user.get("id"),
                exc,
            )

    if phone:
        try:
            await send_text_sms(phone, sms_text)
        except Exception as exc:
            logger.warning(
                "security_sms_failed event=%s user_id=%s err=%s",
                event_name,
                user.get("id"),
                exc,
            )


# ---------------------------------------------------------------------------
# Public notifications
# ---------------------------------------------------------------------------


async def send_new_device_notification(
    user: dict[str, Any],
    session: dict[str, Any],
) -> None:
    """Notify the user that a login came from a previously-unseen device."""
    ip = session.get("ip_address") or "неизвестен"
    ua = session.get("user_agent") or "неизвестно"
    subject = "Вход с нового устройства"
    email_body = (
        "Здравствуйте!\n\n"
        "Зафиксирован вход в ваш аккаунт CarCraft с нового устройства.\n"
        f"IP-адрес: {ip}\n"
        f"Устройство: {ua}\n\n"
        "Если это были вы — действий не требуется. Если нет — срочно "
        "смените пароль и отзовите все сессии в личном кабинете."
    )
    sms_text = (
        f"CarCraft: вход с нового устройства (IP {ip}). "
        "Если это не вы — отзовите сессии в ЛК."
    )
    await _dispatch(
        user,
        event_name="new_device",
        subject=subject,
        email_body=email_body,
        sms_text=sms_text,
    )


async def send_mfa_disabled_notification(user: dict[str, Any]) -> None:
    """Notify the user that two-factor authentication has been disabled."""
    subject = "Двухфакторная аутентификация отключена"
    email_body = (
        "Здравствуйте!\n\n"
        "В вашем аккаунте CarCraft отключена двухфакторная аутентификация.\n"
        "Если это сделали не вы — срочно войдите в личный кабинет, "
        "измените пароль и повторно включите 2FA."
    )
    sms_text = (
        "CarCraft: 2FA отключена. Если это не вы — срочно смените пароль."
    )
    await _dispatch(
        user,
        event_name="mfa_disabled",
        subject=subject,
        email_body=email_body,
        sms_text=sms_text,
    )


async def send_sessions_revoked_all_notification(user: dict[str, Any]) -> None:
    """Notify the user that every active session has been revoked."""
    subject = "Все сессии завершены"
    email_body = (
        "Здравствуйте!\n\n"
        "Все активные сессии вашего аккаунта CarCraft были завершены. "
        "Для дальнейшей работы потребуется повторный вход.\n"
        "Если вы не инициировали это действие — смените пароль."
    )
    sms_text = (
        "CarCraft: все сессии завершены. Если это не вы — смените пароль."
    )
    await _dispatch(
        user,
        event_name="sessions_revoked_all",
        subject=subject,
        email_body=email_body,
        sms_text=sms_text,
    )


async def send_refresh_reuse_notification(
    user: dict[str, Any],
    sessions_killed: int,
) -> None:
    """Notify the user that a refresh-token reuse was detected (possible theft)."""
    subject = "Обнаружена попытка повторного использования токена"
    email_body = (
        "Здравствуйте!\n\n"
        "Обнаружена попытка повторного использования refresh-токена — "
        "возможно, ваши данные были скомпрометированы.\n"
        f"В целях безопасности завершены все активные сессии "
        f"({sessions_killed}). Пожалуйста, войдите заново и смените пароль."
    )
    sms_text = (
        "CarCraft: обнаружена подозрительная активность, "
        f"завершено сессий: {sessions_killed}. Смените пароль."
    )
    await _dispatch(
        user,
        event_name="refresh_reuse",
        subject=subject,
        email_body=email_body,
        sms_text=sms_text,
    )
