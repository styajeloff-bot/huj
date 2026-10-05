"""Add independent PDF metadata to preliminary and final leasing proposals.

Revision ID: 115
Revises: 114
Create Date: 2026-09-09
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "115"
down_revision: str | None = "114"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("leasing_proposals", sa.Column("pdf_s3_key", sa.Text(), nullable=True))
    op.add_column("leasing_proposals", sa.Column("pdf_file_name", sa.String(255), nullable=True))
    op.add_column("leasing_proposals", sa.Column("pdf_size", sa.Integer(), nullable=True))
    op.add_column(
        "leasing_proposals",
        sa.Column("pdf_uploaded_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("leasing_proposals", "pdf_uploaded_at")
    op.drop_column("leasing_proposals", "pdf_size")
    op.drop_column("leasing_proposals", "pdf_file_name")
    op.drop_column("leasing_proposals", "pdf_s3_key")
