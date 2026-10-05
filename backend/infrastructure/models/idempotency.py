"""Durable receipts for application creation requests."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from infrastructure.models import Base


class IdempotencyKey(Base):
    __tablename__ = "application_create_idempotency_keys"
    __table_args__ = (
        sa.UniqueConstraint(
            "endpoint",
            "idempotency_key",
            name="uq_application_create_idempotency_endpoint_key",
        ),
        sa.CheckConstraint(
            "status IN ('in_progress', 'succeeded', 'failed')",
            name="ck_application_create_idempotency_status",
        ),
        sa.Index("idx_application_create_idempotency_expires_at", "expires_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
        server_default=sa.text("gen_random_uuid()"),
    )
    idempotency_key: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    endpoint: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    status: Mapped[str] = mapped_column(sa.String(20), nullable=False)
    request_hash: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    response_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False)
