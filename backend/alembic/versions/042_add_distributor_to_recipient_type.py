"""Add distributor to recipient_type enum

Revision ID: 042
Revises: 041
Create Date: 2026-05-28 14:55:00
"""

from __future__ import annotations

from alembic import op

revision = "042"
down_revision = "041"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE recipient_type ADD VALUE 'distributor'")


def downgrade() -> None:
    # PostgreSQL does not support removing values from an enum.
    # To downgrade we'd need to recreate the enum, which is risky
    # in production. We leave the value in place — it is harmless.
    pass
