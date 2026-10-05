"""SQLAlchemy ORM for the СОПД render cache."""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from infrastructure.models import Base


class SopdRenderedPdf(Base):
    """One filled СОПД PDF, keyed by (template_hash, context_hash).

    See ``alembic/versions/007_sopd_rendered_pdfs.py`` for the rationale.
    """

    __tablename__ = "sopd_rendered_pdfs"

    template_hash: Mapped[str] = mapped_column(
        sa.String(64), primary_key=True
    )
    context_hash: Mapped[str] = mapped_column(
        sa.String(64), primary_key=True
    )
    s3_key: Mapped[str] = mapped_column(sa.Text, nullable=False)
    created_at: Mapped[sa.DateTime] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=sa.func.current_timestamp(),
        nullable=False,
    )
