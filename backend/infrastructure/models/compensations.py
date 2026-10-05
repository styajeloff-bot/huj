"""SQLAlchemy ORM model for the compensations table."""
from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, synonym

from infrastructure.models import Base
from infrastructure.models.enums import (
    calculation_base_enum,
    compensation_status_enum,
    compensation_value_type_enum,
    payer_type_enum,
    payment_schedule_type_enum,
    recipient_type_enum,
)


class CompensationModel(Base):
    """ORM model for support compensations."""

    __tablename__ = "compensations"
    __table_args__ = (
        sa.Index("idx_compensations_applied_support", "applied_support_id"),
        sa.Index("idx_compensations_status", "status"),
        sa.Index("idx_compensations_payer", "payer"),
        sa.Index("idx_compensations_recipient", "recipient"),
        sa.Index("idx_compensations_due_date", "due_date"),
        sa.Index("idx_compensations_application_id", "application_id"),
        sa.Index("idx_compensations_exchange_request_id", "exchange_request_id"),
        sa.CheckConstraint(
            "source IN ('platform', 'exchange')",
            name="ck_compensations_source",
        ),
        sa.CheckConstraint(
            "("
            "source = 'platform' AND application_id IS NOT NULL "
            "AND exchange_request_id IS NULL"
            ") OR ("
            "source = 'exchange' AND exchange_request_id IS NOT NULL "
            "AND application_id IS NULL"
            ")",
            name="ck_compensations_exchange_source_link",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    applied_support_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("application_applied_supports.id", ondelete="CASCADE"),
        nullable=False,
    )
    application_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("leasing_applications.id", ondelete="CASCADE"),
        nullable=True,
    )
    exchange_request_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("exchange_requests.id", ondelete="CASCADE"),
        nullable=True,
    )
    source: Mapped[str] = mapped_column(
        sa.String(20),
        nullable=False,
        server_default=sa.text("'platform'"),
    )
    product_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    vehicle_id = synonym("product_id")

    payer: Mapped[str] = mapped_column(payer_type_enum, nullable=False)
    recipient: Mapped[str] = mapped_column(recipient_type_enum, nullable=False)

    calculation_base: Mapped[str] = mapped_column(calculation_base_enum, nullable=False)
    calculation_base_amount: Mapped[sa.Numeric] = mapped_column(
        sa.Numeric(15, 2), nullable=False, server_default=sa.text("0")
    )

    value_type: Mapped[str] = mapped_column(compensation_value_type_enum, nullable=False)
    value: Mapped[sa.Numeric] = mapped_column(sa.Numeric(15, 2), nullable=False)

    min_amount: Mapped[sa.Numeric | None] = mapped_column(sa.Numeric(15, 2), nullable=True)
    max_amount: Mapped[sa.Numeric | None] = mapped_column(sa.Numeric(15, 2), nullable=True)
    min_percent: Mapped[sa.Numeric | None] = mapped_column(sa.Numeric(10, 4), nullable=True)
    max_percent: Mapped[sa.Numeric | None] = mapped_column(sa.Numeric(10, 4), nullable=True)

    amount: Mapped[sa.Numeric] = mapped_column(
        sa.Numeric(15, 2), nullable=False, server_default=sa.text("0")
    )

    status: Mapped[str] = mapped_column(
        compensation_status_enum, nullable=False, server_default=sa.text("'under_review'")
    )

    payment_schedule_type: Mapped[str] = mapped_column(
        payment_schedule_type_enum, nullable=False, server_default=sa.text("'days_count'")
    )
    payment_schedule_period: Mapped[str | None] = mapped_column(sa.String(20), nullable=True)
    payment_schedule_value: Mapped[str | None] = mapped_column(sa.String(50), nullable=True)
    due_date: Mapped[sa.Date | None] = mapped_column(sa.Date, nullable=True)
    paid_at: Mapped[sa.DateTime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)

    documents: Mapped[list | None] = mapped_column(
        JSONB, server_default=sa.text("'[]'"), nullable=True
    )
    acceptance_comment: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    rejection_comment: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    comment: Mapped[str | None] = mapped_column(sa.Text, nullable=True)

    created_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True
    )
    updated_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True
    )


class CompensationTemplateModel(Base):
    """ORM model for compensation templates bound to support programs."""

    __tablename__ = "compensation_templates"
    __table_args__ = (
        sa.Index("idx_compensation_templates_support", "support_program_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
        server_default=sa.text("gen_random_uuid()"),
    )
    support_program_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("support_programs.id", ondelete="CASCADE"),
        nullable=False,
    )

    payer: Mapped[str] = mapped_column(payer_type_enum, nullable=False)
    recipient: Mapped[str] = mapped_column(recipient_type_enum, nullable=False)
    calculation_base: Mapped[str] = mapped_column(calculation_base_enum, nullable=False)
    value_type: Mapped[str] = mapped_column(compensation_value_type_enum, nullable=False)
    value: Mapped[sa.Numeric] = mapped_column(sa.Numeric(15, 2), nullable=False)

    min_amount: Mapped[sa.Numeric | None] = mapped_column(sa.Numeric(15, 2), nullable=True)
    max_amount: Mapped[sa.Numeric | None] = mapped_column(sa.Numeric(15, 2), nullable=True)
    min_percent: Mapped[sa.Numeric | None] = mapped_column(sa.Numeric(10, 4), nullable=True)
    max_percent: Mapped[sa.Numeric | None] = mapped_column(sa.Numeric(10, 4), nullable=True)

    payment_schedule_type: Mapped[str] = mapped_column(
        payment_schedule_type_enum, nullable=False, server_default=sa.text("'days_count'")
    )
    payment_schedule_period: Mapped[str | None] = mapped_column(sa.String(20), nullable=True)
    payment_schedule_value: Mapped[str | None] = mapped_column(sa.String(50), nullable=True)
    comment: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True
    )
    updated_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True
    )
