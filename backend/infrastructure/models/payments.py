"""SQLAlchemy ORM models for payment-related tables."""

from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from infrastructure.models import Base
from infrastructure.models.enums import (
    payment_status_enum,
    payment_type_enum,
    purchase_status_enum,
    purchase_type_enum,
)


class PurchaseOrder(Base):
    """ORM model for the purchase_orders table."""

    __tablename__ = "purchase_orders"
    __table_args__ = (
        sa.Index("idx_purchase_orders_status", "status"),
        sa.Index("idx_purchase_orders_user_id", "user_id"),
        sa.Index("idx_purchase_orders_product_id", "product_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("users.id"),
        nullable=False,
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("special_equipment_products.id"),
        nullable=False,
    )
    purchase_type: Mapped[str] = mapped_column(purchase_type_enum, nullable=False)
    status: Mapped[str] = mapped_column(
        purchase_status_enum, server_default="reserved", nullable=False
    )
    total_price: Mapped[sa.Numeric] = mapped_column(sa.Numeric(15, 2), nullable=False)
    paid_amount: Mapped[sa.Numeric] = mapped_column(
        sa.Numeric(15, 2), server_default=sa.text("0"), nullable=False
    )
    remaining_amount: Mapped[sa.Numeric] = mapped_column(
        sa.Numeric(15, 2), server_default=sa.text("0"), nullable=False
    )
    leasing_application_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("leasing_applications.id"),
        nullable=True,
    )
    cancellation_reason: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    cancellation_requested_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.current_timestamp(), nullable=True
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.current_timestamp(), nullable=True
    )


class Payment(Base):
    """ORM model for the payments table."""

    __tablename__ = "payments"
    __table_args__ = (
        sa.Index("idx_payments_expires_at", "expires_at"),
        sa.Index("idx_payments_fiscal_status", "fiscal_status"),
        sa.Index("idx_payments_gateway_transaction_id", "gateway_transaction_id"),
        sa.Index("idx_payments_purchase_order_id", "purchase_order_id"),
        sa.Index("idx_payments_status", "status"),
        sa.Index("idx_payments_user_id", "user_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    purchase_order_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("purchase_orders.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("users.id"),
        nullable=False,
    )
    payment_type: Mapped[str] = mapped_column(payment_type_enum, nullable=False)
    amount: Mapped[sa.Numeric] = mapped_column(sa.Numeric(15, 2), nullable=False)
    status: Mapped[str] = mapped_column(
        payment_status_enum, server_default="processing", nullable=False
    )
    gateway_transaction_id: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    gateway_response: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    receipt_url: Mapped[str | None] = mapped_column(sa.String(500), nullable=True)
    receipt_s3_key: Mapped[str | None] = mapped_column(sa.String(500), nullable=True)
    error_message: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.current_timestamp(), nullable=True
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.current_timestamp(), nullable=True
    )
    payment_method: Mapped[str | None] = mapped_column(sa.String(20), nullable=True)
    fiscal_status: Mapped[str | None] = mapped_column(sa.String(30), nullable=True)
    fiscal_receipt_id: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    fiscal_response: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    fiscal_retry_count: Mapped[int | None] = mapped_column(
        sa.Integer, server_default=sa.text("0"), nullable=True
    )
    fiscal_error_message: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)


class LeasingPaymentSchedule(Base):
    """ORM model for the leasing_payment_schedule table."""

    __tablename__ = "leasing_payment_schedule"
    __table_args__ = (
        sa.Index("idx_leasing_schedule_due_date", "due_date"),
        sa.Index("idx_leasing_schedule_order_id", "purchase_order_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    purchase_order_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("purchase_orders.id", ondelete="CASCADE"),
        nullable=False,
    )
    payment_number: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    due_date: Mapped[sa.Date] = mapped_column(sa.Date, nullable=False)
    amount: Mapped[sa.Numeric] = mapped_column(sa.Numeric(15, 2), nullable=False)
    principal: Mapped[sa.Numeric | None] = mapped_column(sa.Numeric(15, 2), nullable=True)
    interest: Mapped[sa.Numeric | None] = mapped_column(sa.Numeric(15, 2), nullable=True)
    payment_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("payments.id"),
        nullable=True,
    )
    is_paid: Mapped[bool | None] = mapped_column(
        sa.Boolean, server_default=sa.false(), nullable=True
    )
    created_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.current_timestamp(), nullable=True
    )
