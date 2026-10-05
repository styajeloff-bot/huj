"""Generic SMTP email sender.

Thin wrapper over :mod:`smtplib` run in a worker thread, using the same
SMTP credentials as :mod:`infrastructure.services.sms` (the SMSC gateway
also goes via SMTP). Port 465 → SMTP_SSL, anything else → STARTTLS.

Callers decide failure policy. For best-effort transactional notifications
(security alerts, application-status updates) catch and log; for
user-initiated actions (admin "send test email") let the exception
propagate so the API can return 5xx.
"""
from __future__ import annotations

import asyncio
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from infrastructure.settings import settings

logger = logging.getLogger("carcraft-backend")


def _send_blocking(
    to: str,
    subject: str,
    body: str,
    *,
    html: str | None = None,
    from_address: str | None = None,
    message_id: str | None = None,
    timeout: float | None = None,
) -> None:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = from_address or settings.smtp_user
    msg["To"] = to
    if message_id is not None:
        msg["Message-ID"] = message_id
    msg.attach(MIMEText(body, "plain", "utf-8"))
    if html:
        msg.attach(MIMEText(html, "html", "utf-8"))

    host, port = settings.smtp_host, settings.smtp_port
    if port == 465:
        with smtplib.SMTP_SSL(host, port, timeout=timeout or 30.0) as smtp:
            smtp.login(settings.smtp_user, settings.smtp_password)
            refused = smtp.send_message(msg)
            if refused:
                raise smtplib.SMTPRecipientsRefused(refused)
    else:
        with smtplib.SMTP(host, port, timeout=timeout or 30.0) as smtp:
            smtp.starttls()
            smtp.login(settings.smtp_user, settings.smtp_password)
            refused = smtp.send_message(msg)
            if refused:
                raise smtplib.SMTPRecipientsRefused(refused)


async def send_email(
    to: str,
    subject: str,
    body: str,
    *,
    html: str | None = None,
    from_address: str | None = None,
    message_id: str | None = None,
    timeout: float | None = None,  # noqa: ASYNC109 - forwarded to blocking SMTP socket in a thread
) -> None:
    """Send an email. Raises on SMTP failure."""
    await asyncio.to_thread(
        _send_blocking, to, subject, body, html=html, from_address=from_address,
        message_id=message_id, timeout=timeout,
    )
    logger.info("email_sent message_id=%s", message_id)
