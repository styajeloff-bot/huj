"""SQLAlchemy ORM models for SOPD partial revocations."""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, INET, JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from infrastructure.models import Base


class SopdRevokeRequest(Base):
    """One SMS-confirmed partial revoke operation for a SOPD."""

    __tablename__ = "sopd_revoke_requests"
    __table_args__ = (
        sa.CheckConstraint(
            "status IN ('pending', 'confirmed', 'cancelled')",
            name="ck_sopd_revoke_requests_status",
        ),
        sa.Index("idx_sopd_revoke_requests_signature_request_id", "signature_request_id"),
        sa.Index("idx_sopd_revoke_requests_user_id", "user_id"),
        sa.Index("idx_sopd_revoke_requests_status", "status"),
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
    status: Mapped[str] = mapped_column(
        sa.String(32), server_default="pending", nullable=False
    )
    selected_leasing_company_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(PGUUID(as_uuid=True)), nullable=False
    )
    revoked_leasing_company_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(PGUUID(as_uuid=True)), nullable=False
    )
    revoked_contractor_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(PGUUID(as_uuid=True)), nullable=False
    )
    excluded_contractor_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(PGUUID(as_uuid=True)), nullable=False
    )
    operators_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    document_s3_key: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    requested_at: Mapped[sa.DateTime] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=sa.func.current_timestamp(),
        nullable=False,
    )
    confirmed_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    revoke_ip: Mapped[str | None] = mapped_column(INET, nullable=True)
    revoke_user_agent: Mapped[str | None] = mapped_column(
        sa.String(512), nullable=True
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


class SopdRevokedOperator(Base):
    """Confirmed revoke fact for one leasing company or contractor."""

    __tablename__ = "sopd_revoked_operators"
    __table_args__ = (
        sa.CheckConstraint(
            "operator_type IN ('leasing_company', 'contractor')",
            name="ck_sopd_revoked_operators_type",
        ),
        sa.UniqueConstraint(
            "signature_request_id",
            "operator_type",
            "leasing_company_id",
            name="uq_sopd_revoked_operators_lc",
        ),
        sa.UniqueConstraint(
            "signature_request_id",
            "operator_type",
            "contractor_id",
            name="uq_sopd_revoked_operators_contractor",
        ),
        sa.Index("idx_sopd_revoked_operators_signature_request_id", "signature_request_id"),
        sa.Index("idx_sopd_revoked_operators_user_id", "user_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    revoke_request_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("sopd_revoke_requests.id", ondelete="CASCADE"),
        nullable=False,
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
    operator_type: Mapped[str] = mapped_column(sa.String(32), nullable=False)
    leasing_company_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("leasing_companies.id", ondelete="SET NULL"),
        nullable=True,
    )
    contractor_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("contractors.id", ondelete="SET NULL"),
        nullable=True,
    )
    operator_name: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    operator_inn: Mapped[str] = mapped_column(sa.String(20), nullable=False)
    created_at: Mapped[sa.DateTime] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=sa.func.current_timestamp(),
        nullable=False,
    )
