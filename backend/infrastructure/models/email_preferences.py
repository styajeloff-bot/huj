"""ORM model for email_preferences table."""

from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from infrastructure.models import Base


class EmailPreferences(Base):
    """One row per user — granular email notification preferences."""

    __tablename__ = "email_preferences"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    application_status_emails: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, server_default=sa.true()
    )
    document_request_emails: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, server_default=sa.true()
    )
    document_status_emails: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, server_default=sa.true()
    )
    leasing_approval_emails: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, server_default=sa.true()
    )
    system_emails: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, server_default=sa.true()
    )
    exchange_emails: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, server_default=sa.true())
    weekly_digest: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, server_default=sa.true()
    )
    marketing_emails: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, server_default=sa.false()
    )
    email_frequency: Mapped[str] = mapped_column(
        sa.String(16), nullable=False, server_default=sa.text("'immediate'")
    )
    created_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.current_timestamp(), nullable=True
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.current_timestamp(), nullable=True
    )
