"""SQLAlchemy ORM model for positions."""

from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from infrastructure.models import Base


class Position(Base):
    """ORM model for the positions table."""

    __tablename__ = "positions"
    __table_args__ = (
        sa.Index("idx_positions_is_active", "is_active"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    code: Mapped[str] = mapped_column(sa.String(100), unique=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(
        sa.Boolean, server_default=sa.true(), default=True, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=sa.func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
        nullable=False,
    )
