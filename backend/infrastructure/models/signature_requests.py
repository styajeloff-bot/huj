"""SQLAlchemy ORM for signature_requests (СОПД / ...)."""
from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from infrastructure.models import Base


class SignatureRequest(Base):
    """One document awaiting signature from a specific user.

    ``subject_snapshot`` is a JSONB blob with ``full_name``, ``inn``,
    ``passport``, ``company_name``, ``company_inn`` frozen at invite time —
    so we can re-render the same template months later even if the company
    or user record changes.

    ``status`` transitions:
        pending → signed_electronic | signed_physical | cancelled.
        signed_electronic | signed_physical → revoked.
    ``revoked`` is a client-initiated legal withdrawal and keeps its own
    audit trail separate from the original signing audit.
    """

    __tablename__ = "signature_requests"
    __table_args__ = (
        sa.CheckConstraint(
            "status IN ('pending', 'signed_electronic', 'signed_physical', "
            "'cancelled', 'revoked')",
            name="ck_signature_requests_status",
        ),
        sa.Index("idx_signature_requests_user_id", "user_id"),
        sa.Index("idx_signature_requests_application_id", "application_id"),
        sa.Index("idx_signature_requests_status", "status"),
        sa.Index(
            "idx_signature_requests_status_revoked", "status",
            postgresql_where=sa.text("status = 'revoked'"),
        ),
        sa.Index(
            "idx_signature_requests_invited_by_user_id", "invited_by_user_id"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    # The applicant who initiated the invite. Kept even after the invited
    # signer is deleted (SET NULL on delete) — the request row survives.
    invited_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    application_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("leasing_applications.id", ondelete="CASCADE"),
        nullable=True,
    )
    document_type: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    status: Mapped[str] = mapped_column(
        sa.String(32), server_default="pending", nullable=False
    )
    signature_method: Mapped[str | None] = mapped_column(
        sa.String(16), nullable=True
    )
    subject_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    signed_pdf_s3_key: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    signing_ip: Mapped[str | None] = mapped_column(INET, nullable=True)
    signing_user_agent: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    sent_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    signed_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    revoked_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    revoke_requested_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    revoke_ip: Mapped[str | None] = mapped_column(INET, nullable=True)
    revoke_user_agent: Mapped[str | None] = mapped_column(
        sa.String(512), nullable=True
    )
    cancelled_at: Mapped[sa.DateTime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[sa.DateTime] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=sa.func.current_timestamp(),
        nullable=False,
    )
    updated_at: Mapped[sa.DateTime] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=sa.func.current_timestamp(),
        nullable=False,
    )
