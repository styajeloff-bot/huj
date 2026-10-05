"""Scoped, user-confirmed passport snapshots for SOPD."""
from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from infrastructure.models import Base


class SopdPassportSnapshot(Base):
    __tablename__ = "sopd_passport_snapshots"
    __table_args__ = (
        sa.UniqueConstraint("application_id", "signer_key", name="uq_sopd_passport_snapshot_signer"),
        sa.UniqueConstraint("signature_request_id", name="uq_sopd_passport_snapshot_request"),
        sa.Index("idx_sopd_passport_snapshots_request", "signature_request_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=sa.text("gen_random_uuid()"))
    application_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), sa.ForeignKey("leasing_applications.id", ondelete="CASCADE"), nullable=False)
    signer_key: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    signature_request_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), sa.ForeignKey("signature_requests.id", ondelete="CASCADE"), nullable=True)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    recognition_fields: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default=sa.text("'{}'::jsonb"))
    recognition_confidence: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default=sa.text("'{}'::jsonb"))
    draft_fields: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default=sa.text("'{}'::jsonb"))
    edited_fields: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list, server_default=sa.text("'[]'::jsonb"))
    confirmed_fields: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    has_unsaved_changes: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, server_default=sa.false())
    confirmed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False, server_default=sa.func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False, server_default=sa.func.current_timestamp())
