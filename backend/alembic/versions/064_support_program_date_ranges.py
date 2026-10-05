"""Add support-program production and delivery date ranges.

Revision ID: 064
Revises: 063
Create Date: 2026-06-29
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "064"
down_revision: str | None = "063"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "support_programs",
        sa.Column("production_date_from", sa.Date(), nullable=True),
    )
    op.add_column(
        "support_programs",
        sa.Column("production_date_to", sa.Date(), nullable=True),
    )
    op.add_column(
        "support_programs",
        sa.Column("delivery_date_from", sa.Date(), nullable=True),
    )
    op.add_column(
        "support_programs",
        sa.Column("delivery_date_to", sa.Date(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("support_programs", "delivery_date_to")
    op.drop_column("support_programs", "delivery_date_from")
    op.drop_column("support_programs", "production_date_to")
    op.drop_column("support_programs", "production_date_from")
