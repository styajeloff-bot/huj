"""ORM model for generic async data-import job tracking.

One row per CSV upload processed by the Taskiq ``data_import.*`` pipeline
(vehicles, exchange requests/bids, distributor-dealer links, ...). The
frontend polls ``GET /api/v1/imports/{job_id}`` against this table.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from infrastructure.models import Base


class DataImportJob(Base):
    """Tracks one end-to-end CSV import (upload → Postgres + Kafka → DWH)."""

    __tablename__ = "data_import_jobs"
    __table_args__ = (
        sa.Index("idx_data_import_jobs_user_id", "user_id"),
        sa.Index("idx_data_import_jobs_status", "status"),
        sa.Index("idx_data_import_jobs_kind", "kind"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )
    kind: Mapped[str] = mapped_column(sa.String(50), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    s3_key: Mapped[str] = mapped_column(sa.String(500), nullable=False)
    filename: Mapped[str | None] = mapped_column(sa.String(500), nullable=True)
    status: Mapped[str] = mapped_column(
        sa.String(20), nullable=False, server_default="queued"
    )
    rows_total: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default="0"
    )
    rows_done: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default="0"
    )
    errors_count: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default="0"
    )
    error_sample: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    params: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    created_at: Mapped[sa.DateTime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )
    updated_at: Mapped[sa.DateTime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )


class DataImportDwhBatch(Base):
    """Durable DWH delivery unit committed with one imported CSV batch."""

    __tablename__ = "data_import_dwh_batches"
    __table_args__ = (
        sa.CheckConstraint(
            "rows_count >= 0",
            name="ck_data_import_dwh_batches_rows_count_non_negative",
        ),
        sa.CheckConstraint(
            "attempts >= 0",
            name="ck_data_import_dwh_batches_attempts_non_negative",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'publishing', 'delivered', 'failed')",
            name="ck_data_import_dwh_batches_status",
        ),
        sa.Index(
            "idx_data_import_dwh_batches_status_next_attempt",
            "status",
            "next_attempt_at",
        ),
        sa.Index(
            "idx_data_import_dwh_batches_job_status",
            "job_id",
            "status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("data_import_jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    payloads: Mapped[dict[str, list[dict[str, Any]]]] = mapped_column(
        JSONB, nullable=False
    )
    rows_count: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    row_errors: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(
        sa.String(20), nullable=False, server_default="pending"
    )
    attempts: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default="0"
    )
    next_attempt_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    locked_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    last_error: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )
    delivered_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
