"""ORM model for the controlled citizenship reference."""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from infrastructure.models import Base


class Citizenship(Base):
    __tablename__ = "citizenship"
    __table_args__ = (sa.UniqueConstraint("code3", name="uq_citizenship_code3"),)

    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True, autoincrement=True)
    code2: Mapped[str] = mapped_column(sa.String(2), nullable=False)
    code3: Mapped[str] = mapped_column(sa.String(3), nullable=False)
    citizenship_name: Mapped[str] = mapped_column(sa.String(255), nullable=False)
