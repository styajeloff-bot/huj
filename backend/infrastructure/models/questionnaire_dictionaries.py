"""Editable beneficiary reference dictionaries."""

from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from infrastructure.models import Base


class _DictionaryColumns:
    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    code: Mapped[str] = mapped_column(sa.String(100), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(sa.Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, server_default=sa.true()
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )


class BeneficialOwnerBasis(_DictionaryColumns, Base):
    __tablename__ = "beneficial_owner_bases"


class BeneficialOwnerAbsenceReason(_DictionaryColumns, Base):
    __tablename__ = "beneficial_owner_absence_reasons"
