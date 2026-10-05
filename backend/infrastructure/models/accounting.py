"""SQLAlchemy ORM models for accounting / bookkeeping reports."""
from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from infrastructure.models import Base


class AccountingReport(Base):
    """ORM model for the `accounting_reports` table.

    One row per (inn) — we always overwrite the latest snapshot.
    """

    __tablename__ = "accounting_reports"
    __table_args__ = (
        sa.Index("idx_accounting_reports_company_id", "company_id"),
        sa.Index("idx_accounting_reports_fetch_status", "fetch_status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    inn: Mapped[str] = mapped_column(sa.String(12), unique=True, nullable=False)
    company_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("companies.id", ondelete="SET NULL"),
        nullable=True,
    )
    provider_name: Mapped[str] = mapped_column(sa.String(40), nullable=False)
    period_years: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    organization: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    balance_sheet: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    financial_result: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    cash_flow: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    capital_change: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    audit_report: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    clarification_url: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    year_files: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    computed_ratios: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    fetch_status: Mapped[str] = mapped_column(
        sa.String(20),
        server_default=sa.text("'pending'"),
        nullable=False,
    )
    fetch_attempts: Mapped[int] = mapped_column(
        sa.Integer, server_default=sa.text("0"), nullable=False
    )
    last_fetch_error: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    last_fetch_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=sa.func.current_timestamp(),
        nullable=True,
    )
    updated_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=sa.func.current_timestamp(),
        nullable=True,
    )
