"""HTTP schemas for email preferences."""
from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class EmailPreferencesPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    application_status_emails: bool | None = None
    document_request_emails: bool | None = None
    document_status_emails: bool | None = None
    leasing_approval_emails: bool | None = None
    system_emails: bool | None = None
    exchange_emails: bool | None = None
    weekly_digest: bool | None = None
    marketing_emails: bool | None = None
    email_frequency: Literal["immediate", "daily", "weekly"] | None = None


class EmailPreferencesBody(BaseModel):
    user_id: UUID
    application_status_emails: bool
    document_request_emails: bool
    document_status_emails: bool
    leasing_approval_emails: bool
    system_emails: bool
    exchange_emails: bool
    weekly_digest: bool
    marketing_emails: bool
    email_frequency: str
    updated_at: datetime | None = None


class EmailPreferencesResponse(BaseModel):
    success: bool = True
    preferences: EmailPreferencesBody


class EmailPreferencesUpdateResponse(BaseModel):
    success: bool = True
    message: str
    preferences: EmailPreferencesBody


# ---------------------------------------------------------------------------
# Admin schemas — test send / stats / logs
# ---------------------------------------------------------------------------


_EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


class TestEmailRequest(BaseModel):
    """Optional override for test-email recipient.

    When ``to`` is omitted, the email is sent to the current user's address.
    Email validation is intentionally permissive — strict validation is the
    SMTP gateway's job. ``EmailStr`` would require the optional
    ``email-validator`` extra, which we don't want as a runtime dep.
    """

    model_config = ConfigDict(extra="forbid")

    to: str | None = Field(default=None, pattern=_EMAIL_PATTERN, max_length=320)


class TestEmailResponse(BaseModel):
    success: bool = True
    sent_to: str
    message: str = "Test email sent successfully"


class EmailFrequencyBreakdown(BaseModel):
    immediate: int = 0
    daily: int = 0
    weekly: int = 0


class EmailStatsBody(BaseModel):
    """Notification delivery intents, including blocks of a digest.

    Sent means accepted by SMTP, not delivered to an inbox or read. The rate
    excludes pending/skipped intents: sent / (sent + terminal failed).
    """

    total_emails: int = 0
    sent_emails: int = 0
    failed_emails: int = 0
    skipped_emails: int = 0
    today_emails: int = 0
    week_emails: int = 0
    delivery_rate: float = 0.0
    subscribers: int = Field(
        default=0,
        description=(
            "Количество пользователей с записью в email_preferences "
            "(база подписчиков)."
        ),
    )
    frequency_breakdown: EmailFrequencyBreakdown = Field(
        default_factory=EmailFrequencyBreakdown
    )


class EmailStatsResponse(BaseModel):
    success: bool = True
    stats: EmailStatsBody
