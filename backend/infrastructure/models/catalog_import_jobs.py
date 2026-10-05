"""ORM model for catalog import job tracking."""
from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from infrastructure.models import Base


class CatalogImportJob(Base):
    """Tracks one end-to-end catalog upload (XLSX → vehicles + images)."""

    __tablename__ = "catalog_import_jobs"
    __table_args__ = (
        sa.Index("idx_catalog_import_jobs_user_id", "user_id"),
        sa.Index("idx_catalog_import_jobs_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )
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
    images_total: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default="0"
    )
    images_done: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default="0"
    )
    images_failed: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default="0"
    )
    error: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    created_at: Mapped[sa.DateTime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    )
    updated_at: Mapped[sa.DateTime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    )
