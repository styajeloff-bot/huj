"""Transactional status history and delivery state for LCA analytics."""

from __future__ import annotations

import uuid
from datetime import date, datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from infrastructure.models import Base


class LeasingCompanyApplicationStatusHistory(Base):
    """One durable LCA status event and its Kafka outbox state."""

    __tablename__ = "leasing_company_application_status_history"
    __table_args__ = (
        sa.Index(
            "idx_lca_status_history_lca_changed_at",
            "lca_id",
            sa.desc("changed_at"),
        ),
        sa.Index(
            "idx_lca_status_history_publish_queue",
            "published_at",
            "next_attempt_at",
        ),
        sa.Index(
            "idx_lca_status_history_dealer_changed_at",
            "dealer_company_id",
            "changed_at",
        ),
        sa.Index(
            "uq_lca_status_history_baseline_lca",
            "lca_id",
            unique=True,
            postgresql_where=sa.text("is_baseline"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=sa.text("gen_random_uuid()"),
    )
    lca_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("leasing_company_applications.id"),
        nullable=False,
    )
    application_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("leasing_applications.id"),
        nullable=True,
    )
    old_status: Mapped[str | None] = mapped_column(sa.String(64), nullable=True)
    new_status: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    changed_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=sa.func.current_timestamp(),
        nullable=False,
    )
    changed_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    reason: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    application_created_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    lca_created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False
    )
    dealer_company_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), nullable=True
    )
    distributor_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), nullable=True
    )
    leasing_company_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), nullable=True
    )
    is_baseline: Mapped[bool] = mapped_column(
        sa.Boolean, server_default=sa.false(), nullable=False
    )
    published_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    publish_attempts: Mapped[int] = mapped_column(
        sa.Integer, server_default=sa.text("0"), nullable=False
    )
    next_attempt_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    last_publish_error: Mapped[str | None] = mapped_column(sa.Text, nullable=True)


class LcaStatusHistoryMetadata(Base):
    """Small persisted control-plane values for the LCA history read model."""

    __tablename__ = "lca_status_history_metadata"

    key: Mapped[str] = mapped_column(sa.String(64), primary_key=True)
    date_value: Mapped[date] = mapped_column(sa.Date, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=sa.func.current_timestamp(),
        nullable=False,
    )
