"""Append-only audit history for administrative company-card changes."""
from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from infrastructure.models import Base


class CompanyChangeHistory(Base):
    """An immutable, transaction-local snapshot of a company-card operation."""

    __tablename__ = "company_change_history"
    __table_args__ = (
        sa.CheckConstraint(
            "action IN ('company_profile_saved', 'company_status_changed', "
            "'distributor_brands_saved', 'leasing_contractors_saved')",
            name="ck_company_change_history_action",
        ),
        sa.Index(
            "idx_company_change_history_company_changed_id_desc",
            "company_id",
            sa.text("changed_at DESC"),
            sa.text("id DESC"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("companies.id", name="fk_company_change_history_company"),
        nullable=False,
    )
    actor_user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("users.id", name="fk_company_change_history_actor"),
        nullable=False,
    )
    actor_display_name: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    action: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    snapshot: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    changed_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.current_timestamp()
    )
