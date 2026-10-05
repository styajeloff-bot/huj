"""Durable notification transport, consumer receipts and SMTP work journal."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from infrastructure.models import Base


class NotificationEventOutbox(Base):
    __tablename__ = "notification_event_outbox"
    __table_args__ = (
        sa.Index(
            "ix_notification_outbox_due",
            "next_attempt_at",
            postgresql_where=sa.text("published_at IS NULL"),
        ),
        sa.Index("ix_notification_outbox_aggregate", "aggregate_id", "sequence"),
    )

    event_id: Mapped[UUID] = mapped_column(primary_key=True)
    sequence: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(), unique=True)
    event_type: Mapped[str] = mapped_column(sa.String(100))
    entity_type: Mapped[str] = mapped_column(sa.String(32))
    entity_id: Mapped[UUID]
    aggregate_id: Mapped[UUID]
    occurrence_key: Mapped[str | None] = mapped_column(sa.String(500), unique=True)
    payload: Mapped[dict] = mapped_column(JSONB)
    occurred_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )
    published_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    publish_attempts: Mapped[int] = mapped_column(server_default="0")
    next_attempt_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )
    last_publish_error: Mapped[str | None] = mapped_column(sa.String(250))


class NotificationEventReceipt(Base):
    """Replay tombstone retained even if a user deletes their inbox item."""

    __tablename__ = "notification_event_receipts"

    event_id: Mapped[UUID] = mapped_column(primary_key=True)
    payload: Mapped[dict] = mapped_column(JSONB)
    processed_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )


class NotificationDocumentUploadGroup(Base):
    """Immutable after closing; its UUID is also the summary event identity."""

    __tablename__ = "notification_document_upload_groups"
    __table_args__ = (
        sa.Index(
            "ix_notification_document_groups_due", "closes_at",
            postgresql_where=sa.text("closed_at IS NULL"),
        ),
        sa.Index(
            "ix_notification_document_groups_scope", "application_id",
            "leasing_company_id", "request_batch_id", "first_upload_at",
        ),
        sa.CheckConstraint(
            "closes_at = first_upload_at + interval '10 minutes'",
            name="ck_notification_document_group_window",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    application_id: Mapped[UUID] = mapped_column(sa.ForeignKey("leasing_applications.id"))
    leasing_company_id: Mapped[UUID] = mapped_column(sa.ForeignKey("leasing_companies.id"))
    request_batch_id: Mapped[UUID]
    first_event_id: Mapped[UUID] = mapped_column(
        sa.ForeignKey("notification_event_receipts.event_id"), unique=True,
    )
    request_number: Mapped[str] = mapped_column(sa.String(100))
    first_upload_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    closes_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(),
    )


class NotificationDocumentUploadMember(Base):
    """Every source fact remains linked; document count uses distinct documents."""

    __tablename__ = "notification_document_upload_members"
    __table_args__ = (
        sa.Index("ix_notification_document_members_group", "group_id"),
    )

    event_id: Mapped[UUID] = mapped_column(
        sa.ForeignKey("notification_event_receipts.event_id"), primary_key=True,
    )
    group_id: Mapped[UUID] = mapped_column(
        sa.ForeignKey("notification_document_upload_groups.id"),
    )
    # Audit identity survives document deletion; never dereference it for access.
    document_id: Mapped[UUID]
    occurred_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))


class NotificationEmailBatch(Base):
    """Persisted message identity and lease; retries reuse its member deliveries."""

    __tablename__ = "notification_email_batches"
    __table_args__ = (
        sa.Index("ix_notification_batches_due", "status", "next_attempt_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(sa.ForeignKey("users.id"))
    delivery_mode: Mapped[str] = mapped_column(sa.String(16))
    status: Mapped[str] = mapped_column(sa.String(32), server_default="pending")
    attempt_count: Mapped[int] = mapped_column(server_default="0")
    next_attempt_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )
    lease_token: Mapped[UUID | None]
    lease_until: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    message_id: Mapped[str] = mapped_column(sa.String(255), unique=True)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )


class NotificationEmailDelivery(Base):
    __tablename__ = "notification_email_deliveries"
    __table_args__ = (
        sa.UniqueConstraint(
            "event_id", "user_id", name="uq_notification_delivery_event_user"
        ),
        sa.Index("ix_notification_deliveries_due", "status", "next_attempt_at"),
        sa.Index("ix_notification_deliveries_batch", "batch_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    notification_id: Mapped[UUID] = mapped_column(sa.ForeignKey("notifications.id"))
    event_id: Mapped[UUID] = mapped_column(
        sa.ForeignKey("notification_event_receipts.event_id")
    )
    user_id: Mapped[UUID] = mapped_column(sa.ForeignKey("users.id"))
    recipient_role: Mapped[str] = mapped_column(sa.String(32))
    recipient_company_id: Mapped[UUID | None]
    batch_id: Mapped[UUID | None] = mapped_column(
        sa.ForeignKey("notification_email_batches.id")
    )
    status: Mapped[str] = mapped_column(sa.String(32), server_default="pending")
    delivery_mode: Mapped[str] = mapped_column(sa.String(16))
    attempt_count: Mapped[int] = mapped_column(server_default="0")
    next_attempt_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    processing_started_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True)
    )
    sent_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    failed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(sa.String(250))
    message_id: Mapped[str | None] = mapped_column(sa.String(255))
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )
