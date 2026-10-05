"""SQLAlchemy ORM model for SOPD operator snapshots."""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from infrastructure.models import Base


class SopdOperatorSnapshot(Base):
    """Operators included into one SOPD at generation/signing time."""

    __tablename__ = "sopd_operator_snapshots"
    __table_args__ = (
        sa.UniqueConstraint(
            "signature_request_id",
            name="uq_sopd_operator_snapshots_signature_request_id",
        ),
        sa.Index("idx_sopd_operator_snapshots_user_id", "user_id"),
        sa.Index("idx_sopd_operator_snapshots_application_id", "application_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    signature_request_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("signature_requests.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    application_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("leasing_applications.id", ondelete="SET NULL"),
        nullable=True,
    )
    leasing_companies: Mapped[list[dict[str, object]]] = mapped_column(
        JSONB, nullable=False
    )
    contractors: Mapped[list[dict[str, object]]] = mapped_column(
        JSONB, nullable=False
    )
    source: Mapped[str] = mapped_column(
        sa.String(64),
        server_default="application_selected_leasing_companies",
        nullable=False,
    )
    created_at: Mapped[sa.DateTime] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=sa.func.current_timestamp(),
        nullable=False,
    )
    updated_at: Mapped[sa.DateTime] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=sa.func.current_timestamp(),
        onupdate=sa.func.current_timestamp(),
        nullable=False,
    )
