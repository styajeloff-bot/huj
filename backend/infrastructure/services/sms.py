"""SMS sending via SMTP gateway (SMSC protocol, matching Express implementation)."""
import asyncio
import logging
import secrets
import smtplib
from datetime import UTC, datetime
from email.mime.text import MIMEText

from infrastructure.settings import settings

logger = logging.getLogger("carcraft-backend")


def is_test_phone(phone: str) -> bool:
    return phone.startswith('+7666')


def get_verification_code(phone: str) -> str:
    return '0000' if is_test_phone(phone) else f'{secrets.randbelow(9000) + 1000}'


def _build_smsc_body(phone: str, code: str, sms_type: str) -> str:
    now = datetime.now(UTC)
    date_str = now.strftime('%d%m%y%H%M')
    digits = phone.replace('+7', '', 1)
    tail = (
        f'Код подтверждения регистрации {code}'
        if sms_type == 'registration'
        else f'Код авторизации {code}'
    )
    return (
        f'{settings.smsc_login}:{settings.smsc_password}'
        f':999:{date_str},0:0,0,CARCRAFT,1:+7{digits}:{tail}'
    )


_SMTP_TIMEOUT_SECONDS = 10


def _send_smtp_blocking(phone: str, code: str, sms_type: str) -> None:
    body = _build_smsc_body(phone, code, sms_type)
    msg = MIMEText(body)
    msg['Subject'] = 'SMS'
    msg['From'] = settings.smtp_user
    msg['To'] = settings.smsc_sender

    host, port = settings.smtp_host, settings.smtp_port
    if port == 465:
        with smtplib.SMTP_SSL(host, port, timeout=_SMTP_TIMEOUT_SECONDS) as smtp:
            smtp.login(settings.smtp_user, settings.smtp_password)
            smtp.send_message(msg)
    else:
        with smtplib.SMTP(host, port, timeout=_SMTP_TIMEOUT_SECONDS) as smtp:
            smtp.starttls()
            smtp.login(settings.smtp_user, settings.smtp_password)
            smtp.send_message(msg)


async def send_verification_sms(phone: str, code: str, sms_type: str = 'login') -> None:
    """Send verification SMS. Raises on failure."""
    await asyncio.to_thread(_send_smtp_blocking, phone, code, sms_type)
    logger.info("SMS sent to %s (type=%s)", phone, sms_type)


def _build_smsc_text_body(phone: str, text: str) -> str:
    """SMSC envelope for arbitrary-text (non-OTP) messages.

    Mirrors :func:`_build_smsc_body` but carries a free-form ``text`` tail
    instead of a templated verification code.
    """
    now = datetime.now(UTC)
    date_str = now.strftime('%d%m%y%H%M')
    digits = phone.replace('+7', '', 1)
    return (
        f'{settings.smsc_login}:{settings.smsc_password}'
        f':999:{date_str},0:0,0,CARCRAFT,1:+7{digits}:{text}'
    )


def _send_text_smtp_blocking(phone: str, text: str) -> None:
    body = _build_smsc_text_body(phone, text)
    msg = MIMEText(body)
    msg['Subject'] = 'SMS'
    msg['From'] = settings.smtp_user
    msg['To'] = settings.smsc_sender

    host, port = settings.smtp_host, settings.smtp_port
    if port == 465:
        with smtplib.SMTP_SSL(host, port, timeout=_SMTP_TIMEOUT_SECONDS) as smtp:
            smtp.login(settings.smtp_user, settings.smtp_password)
            smtp.send_message(msg)
    else:
        with smtplib.SMTP(host, port, timeout=_SMTP_TIMEOUT_SECONDS) as smtp:
            smtp.starttls()
            smtp.login(settings.smtp_user, settings.smtp_password)
            smtp.send_message(msg)


async def send_text_sms(phone: str, text: str) -> None:
    """Send an arbitrary-text SMS via the SMSC gateway. Raises on failure.

    Used for transactional security notifications (new-device alerts,
    MFA-disabled, session revocation). The OTP path continues to go
    through :func:`send_verification_sms` unchanged.
    """
    await asyncio.to_thread(_send_text_smtp_blocking, phone, text)
    logger.info("SMS text sent to %s", phone)
