"""SQLAlchemy ORM models for SOPD contractor directory."""
from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from infrastructure.models import Base


class Contractor(Base):
    """Directory row for personal-data processors used by leasing companies."""

    __tablename__ = "contractors"
    __table_args__ = (
        sa.UniqueConstraint("inn", name="uq_contractors_inn"),
        sa.Index("idx_contractors_inn", "inn"),
        sa.Index("idx_contractors_name", "name"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    inn: Mapped[str] = mapped_column(sa.String(12), nullable=False)
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


class LeasingCompanyContractor(Base):
    """Many-to-many link between leasing companies and contractors."""

    __tablename__ = "leasing_company_contractors"
    __table_args__ = (
        sa.UniqueConstraint(
            "leasing_company_id",
            "contractor_id",
            name="uq_leasing_company_contractors_pair",
        ),
        sa.Index(
            "idx_leasing_company_contractors_lc_id",
            "leasing_company_id",
        ),
        sa.Index(
            "idx_leasing_company_contractors_contractor_id",
            "contractor_id",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    leasing_company_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("leasing_companies.id", ondelete="CASCADE"),
        nullable=False,
    )
    contractor_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        sa.ForeignKey("contractors.id", ondelete="CASCADE"),
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
