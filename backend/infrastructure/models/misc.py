"""SQLAlchemy ORM models for miscellaneous domain tables."""

from __future__ import annotations

import uuid
from datetime import date, datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from infrastructure.models import Base
from infrastructure.models.enums import notification_type_enum


class Notification(Base):
    """ORM model for the notifications table."""

    __tablename__ = "notifications"
    __table_args__ = (
        sa.Index("idx_notifications_user", "user_id"),
        sa.Index("uq_notifications_event_user", "event_id", "user_id", unique=True,
                 postgresql_where=sa.text("event_id IS NOT NULL")),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("users.id"),
        nullable=True,
    )
    type: Mapped[str] = mapped_column(notification_type_enum, nullable=False)
    title: Mapped[str] = mapped_column(sa.String(500), nullable=False)
    message: Mapped[str] = mapped_column(sa.Text, nullable=False)
    data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    event_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True))
    deleted_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    is_read: Mapped[bool | None] = mapped_column(
        sa.Boolean, server_default=sa.false(), nullable=True
    )
    application_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("leasing_applications.id"),
        nullable=True,
    )
    action_url: Mapped[str | None] = mapped_column(sa.String(1000), nullable=True)
    created_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.current_timestamp(), nullable=True
    )
    read_at: Mapped[sa.DateTime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)


class LeasingCalculation(Base):
    """ORM model for the leasing_calculations table."""

    __tablename__ = "leasing_calculations"
    __table_args__ = (
        sa.Index("idx_leasing_calculations_user_id", "user_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    params: Mapped[dict] = mapped_column(JSONB, nullable=False)
    calculation: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.current_timestamp(), nullable=True
    )


class LeasingRate(Base):
    """ORM model for the leasing_rates table."""

    __tablename__ = "leasing_rates"
    __table_args__ = (
        sa.Index("idx_leasing_rates_id", "id"),
        sa.Index("idx_leasing_rates_period", "date_from", "date_to"),
        sa.Index(
            "uq_leasing_rates_current",
            sa.text("(date_to IS NULL)"),
            unique=True,
            postgresql_where=sa.text("date_to IS NULL"),
        ),
        sa.CheckConstraint(
            "date_to IS NULL OR date_to > date_from",
            name="ck_leasing_rates_valid_period",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    date_from: Mapped[date] = mapped_column(sa.Date, nullable=False, default=date.today)
    date_to: Mapped[date | None] = mapped_column(sa.Date, nullable=True)
    key_rate: Mapped[float] = mapped_column(sa.Double, nullable=False)
    surcharge: Mapped[float] = mapped_column(sa.Double, nullable=False)
    vat_rate: Mapped[float] = mapped_column(sa.Double, nullable=False)
    profit_tax_rate: Mapped[float] = mapped_column(sa.Double, nullable=False)
